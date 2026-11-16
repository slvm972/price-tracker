"""
catalog_filters.py — очистка данных перед публикацией каталога (data.js).

Правила применяются при сборке витрины, БД не меняется: исходные цены
сохраняются как есть, поэтому пороги можно подбирать без перекачки данных.

Что отсеивается:
  - цены-заглушки (0.01, 0.1 ...) — порог MIN_PRICE;
  - внутренние коды сетей вместо штрихкода (короткие/нечисловые) — их нельзя
    сравнивать между сетями: один и тот же код в разных сетях = разные товары;
  - не-товары (купоны, проездные, услуги) — NON_PRODUCT_WORDS;
  - статистические выбросы цены относительно медианы по сетям.
"""

import re
from statistics import median

MIN_PRICE = 0.5
MIN_BARCODE_LEN = 8
# Внутренние коды магазинов (весовые товары, «свободные» позиции): сети дополняют
# номер позиции нулями до 13 знаков как 729 + 000000 + 4 цифры. Один и тот же код
# в разных сетях означает разные товары (киви, шпинат, дрон...), сравнивать нельзя.
INTERNAL_CODE_PREFIX = "729000000"
OUTLIER_FACTOR = 5.0        # от медианы: [median / 5, median * 5], если сетей >= 3
TWO_CHAIN_MAX_RATIO = 5.0  # если сетей ровно 2: слишком большой разброс -> товар убираем
UNVERIFIED_WEIGHT_RATIO = 3.0  # см. drop_unverified_weight_mismatches ниже

NON_PRODUCT_WORDS = ("קופון", "מנוי", "דמי משלוח", "תו קנייה", "תווי קנייה")

_QTY_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(.*)$")
_EMPTY_UNITS = {"", "unknown", "יחידות", "יחידה", "יח", "יח'"}


def is_internal_code(code):
    code = (code or "").strip()
    return len(code) == 13 and code.startswith(INTERNAL_CODE_PREFIX)


def is_valid_barcode(code, min_len=MIN_BARCODE_LEN):
    code = (code or "").strip()
    return code.isdigit() and len(code) >= min_len and not is_internal_code(code)


def is_valid_price(price, min_price=MIN_PRICE):
    try:
        return float(price) >= min_price
    except (TypeError, ValueError):
        return False


def is_non_product(name):
    name = name or ""
    return any(word in name for word in NON_PRODUCT_WORDS)


def clean_size(size):
    """'0.00 יחידות' -> '', '0.00 100 גרם' -> '100 גרם', 'Unknown' -> ''."""
    s = (size or "").strip()
    m = _QTY_RE.match(s)
    if m and float(m.group(1)) == 0:
        s = m.group(2).strip()
    return "" if s.lower() in _EMPTY_UNITS else s


def drop_price_outliers(prices):
    """prices: {сеть: цена}. Возвращает словарь без выбросов (пустой — товар убрать)."""
    n = len(prices)
    if n < 2:
        return dict(prices)
    values = list(prices.values())
    if n == 2:
        lo, hi = min(values), max(values)
        return {} if lo <= 0 or hi / lo > TWO_CHAIN_MAX_RATIO else dict(prices)
    med = median(values)
    return {
        k: v for k, v in prices.items()
        if med / OUTLIER_FACTOR <= v <= med * OUTLIER_FACTOR
    }


def drop_unverified_weight_mismatches(ch, weighted_map):
    """
    ch: {сеть: цена} — изменяется на месте, убирает отдельные цены (не весь товар).
    weighted_map: {сеть: 0/1/None} — признак «весовой товар» (bIsWeighted) у выбранного
    филиала этой сети для этого товара.

    У части сетей (CityMarketShops, Wolt) парсер не считывает bIsWeighted, а у отдельных
    старых записей (один магазин, не обновлялся после добавления этого поля) оно тоже
    None. Когда у такой сети цена сильно (в UNVERIFIED_WEIGHT_RATIO раз и больше)
    расходится с ценой сетей, где признак ИЗВЕСТЕН — единица измерения не подтверждена,
    сравнивать её нельзя: убираем только эту цену, товар с остальными сетями остаётся.
    Возвращает число убранных цен.
    """
    known = {k: v for k, v in ch.items() if weighted_map.get(k) is not None}
    if len(known) < 2:
        return 0
    med = median(known.values())
    if med <= 0:
        return 0
    removed = 0
    for k in list(ch):
        if weighted_map.get(k) is None:
            v = ch[k]
            if v >= med * UNVERIFIED_WEIGHT_RATIO or v <= med / UNVERIFIED_WEIGHT_RATIO:
                del ch[k]
                removed += 1
    return removed


def build_catalog(rows, min_chains=2, min_price=MIN_PRICE, min_barcode_len=MIN_BARCODE_LEN,
                  branch_agg="median"):
    """
    branch_agg — как свести цены разных филиалов одной сети к одной цене:
      "median" (по умолчанию) — медиана по филиалам (нижняя из двух средних), устойчива к
                одному «странному» филиалу с заниженной ценой;
      "min"     — самая низкая цена среди филиалов (прежнее поведение).
    rows — итерируемое со строками (dict или sqlite3.Row) с полями:
      barcode, name, brand, size, retailer, price, previous_price.
    Возвращает (catalog, stats). Формат элемента каталога не меняется:
      {"c", "n", "m", "s", "ch": {сеть: цена}, "prev": {сеть: прошлая цена}}.
    """
    stats = {
        "rows": 0,
        "internal_code": 0,
        "bad_barcode": 0,
        "bad_price": 0,
        "non_product": 0,
        "outlier_prices": 0,
        "items_dropped_outliers": 0,
        "items_dropped_min_chains": 0,
        "items_out": 0,
        "branch_min_outliers": 0,
        "unverified_weight_dropped": 0,
    }
    by_barcode = {}

    for row in rows:
        stats["rows"] += 1
        barcode = (row["barcode"] or "").strip()
        if is_internal_code(barcode):
            stats["internal_code"] += 1
            continue
        if not is_valid_barcode(barcode, min_barcode_len):
            stats["bad_barcode"] += 1
            continue
        price = row["price"]
        if not is_valid_price(price, min_price):
            stats["bad_price"] += 1
            continue
        if is_non_product(row["name"]):
            stats["non_product"] += 1
            continue

        item = by_barcode.get(barcode)
        if item is None:
            item = by_barcode[barcode] = {
                "c": barcode,
                "n": row["name"],
                "m": row["brand"] or "",
                "s": clean_size(row["size"]),
                "ch": {},
                "prev": {},
            }
        elif not item["s"]:
            item["s"] = clean_size(row["size"])

        retailer = row["retailer"]
        prev = row["previous_price"]
        if prev is None or not is_valid_price(prev, min_price):
            prev = None
        weighted = row["is_weighted"] if "is_weighted" in row.keys() else None
        item.setdefault("_b", {}).setdefault(retailer, []).append((price, prev, weighted))

    catalog = []
    for item in by_barcode.values():
        branches = item.pop("_b", None)
        weighted_map = {}
        if branches:
            for retailer, lst in branches.items():
                lst.sort(key=lambda t: t[0])
                chosen = lst[0] if branch_agg == "min" else lst[(len(lst) - 1) // 2]
                item["ch"][retailer] = chosen[0]
                if chosen[1] is not None:
                    item["prev"][retailer] = chosen[1]
                weighted_map[retailer] = chosen[2]
                if len(lst) >= 3 and lst[0][0] < 0.5 * chosen[0]:
                    stats["branch_min_outliers"] += 1
        stats["unverified_weight_dropped"] += drop_unverified_weight_mismatches(
            item["ch"], weighted_map)
        cleaned = drop_price_outliers(item["ch"])
        stats["outlier_prices"] += len(item["ch"]) - len(cleaned)
        if not cleaned:
            stats["items_dropped_outliers"] += 1
            continue
        item["ch"] = cleaned
        item["prev"] = {k: v for k, v in item["prev"].items() if k in cleaned}
        if len(cleaned) < min_chains:
            stats["items_dropped_min_chains"] += 1
            continue
        catalog.append(item)

    catalog.sort(key=lambda i: (i["n"], i["c"]))  # стабильный порядок: чище diff data.js
    stats["items_out"] = len(catalog)
    return catalog, stats
