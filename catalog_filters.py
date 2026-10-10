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
OUTLIER_FACTOR = 5.0        # от медианы: [median / 5, median * 5], если сетей >= 3
TWO_CHAIN_MAX_RATIO = 10.0  # если сетей ровно 2: слишком большой разброс -> товар убираем

NON_PRODUCT_WORDS = ("קופון", "מנוי", "דמי משלוח", "תו קנייה", "תווי קנייה")

_QTY_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(.*)$")
_EMPTY_UNITS = {"", "unknown", "יחידות", "יחידה", "יח", "יח'"}


def is_valid_barcode(code, min_len=MIN_BARCODE_LEN):
    code = (code or "").strip()
    return code.isdigit() and len(code) >= min_len


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


def build_catalog(rows, min_chains=2, min_price=MIN_PRICE, min_barcode_len=MIN_BARCODE_LEN):
    """
    rows — итерируемое со строками (dict или sqlite3.Row) с полями:
      barcode, name, brand, size, retailer, price, previous_price.
    Возвращает (catalog, stats). Формат элемента каталога не меняется:
      {"c", "n", "m", "s", "ch": {сеть: цена}, "prev": {сеть: прошлая цена}}.
    """
    stats = {
        "rows": 0,
        "bad_barcode": 0,
        "bad_price": 0,
        "non_product": 0,
        "outlier_prices": 0,
        "items_dropped_outliers": 0,
        "items_dropped_min_chains": 0,
        "items_out": 0,
    }
    by_barcode = {}

    for row in rows:
        stats["rows"] += 1
        barcode = (row["barcode"] or "").strip()
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
        existing = item["ch"].get(retailer)
        if existing is None or price < existing:
            item["ch"][retailer] = price
            prev = row["previous_price"]
            if prev is not None and is_valid_price(prev, min_price):
                item["prev"][retailer] = prev
            else:
                item["prev"].pop(retailer, None)

    catalog = []
    for item in by_barcode.values():
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
