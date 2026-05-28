"""
make_viewer.py — читает данные из SQLite и создаёт price_viewer.html через template.html.
"""

import json, time
import database

print("Читаем данные из базы данных...")
database.init_db()

rows = database.get_latest_prices(limit=500_000)

if not rows:
    print("База данных пуста!")
    print("Сначала запустите: python download_all.py")
    exit(1)

catalog_by_barcode = {}
for row in rows:
    barcode = row["barcode"]
    retailer = row["retailer"]
    price = row["price"]
    previous_price = row.get("previous_price")
    if barcode not in catalog_by_barcode:
        catalog_by_barcode[barcode] = {
            "c": barcode,
            "n": row["name"],
            "m": row["brand"] or "",
            "s": row["size"] or "",
            "ch": {},
            "prev": {},
        }
    existing = catalog_by_barcode[barcode]["ch"].get(retailer)
    if existing is None or price < existing:
        catalog_by_barcode[barcode]["ch"][retailer] = price
        if previous_price is not None:
            catalog_by_barcode[barcode]["prev"][retailer] = previous_price

catalog = list(catalog_by_barcode.values())

from collections import Counter

chain_counts = Counter()
for item in catalog:
    for ch in item["ch"]:
        chain_counts[ch] += 1
chains_found = [ch for ch, _ in chain_counts.most_common()]

in_multiple = sum(1 for r in catalog if len(r["ch"]) >= 2)
print(f"  Уникальных штрихкодов: {len(catalog):,}")
print(f"  Товаров в 2+ сетях:    {in_multiple:,}")
print(f"  Сети: {', '.join(chains_found)}")

CHAIN_COLORS = {
    "Victory": "#58a6ff",
    "Shufersal": "#ff7b72",
    "Yohananof": "#ffa657",
    "Osher Ad": "#3fb950",
    "Tiv Taam": "#d2a8ff",
    "Hazi Hinam": "#79c0ff",
    "YaynoeBitan": "#f0883e",
    "Keshet": "#56d364",
    "Rami Levy": "#ff6e96",
}

D = json.dumps(catalog, ensure_ascii=False)
C = json.dumps(
    {ch: CHAIN_COLORS.get(ch, "#8b949e") for ch in chains_found}, ensure_ascii=False
)
CH = json.dumps(chains_found, ensure_ascii=False)
UPD = time.strftime("%d.%m.%Y %H:%M")
stats = database.get_db_stats()

# ── Читаем чистый HTML шаблон из внешнего файла ──────────────────
with open("template.html", "r", encoding="utf-8") as f:
    html_template = f.read()

# Подставляем собранные данные
html = (html_template
    .replace("__UPD__",    UPD)
    .replace("__STATS__",  str(stats["products"]))
    .replace("__PRICES__", str(stats["prices"]))
    .replace("__DATA__",   D)
    .replace("__COLORS__", C)
    .replace("__CHAINS__", CH)
)

# Записываем готовый результат
with open("price_viewer.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✓ Создан price_viewer.html с поддержкой иврита и русского языка")
print(f"  Товаров: {len(catalog):,} | В 2+ сетях: {in_multiple:,}")