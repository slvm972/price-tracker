"""
make_viewer.py — читает данные из SQLite и создаёт data.js
для frontend-репозитория pricetracker-interface-found.

Интерфейс price_viewer.html находится только во frontend-репозитории.
Этот скрипт больше не генерирует HTML.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import database

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def to_israel_local(raw) -> str:
    """
    Convert UTC timestamp string from DB (YYYY-MM-DD HH:MM:SS) to Asia/Jerusalem.
    Falls back to current Israel time if parsing fails or value is empty.
    """
    if raw:
        s = str(raw).strip().replace("T", " ")
        if s.endswith("Z"):
            s = s[:-1].strip()
        if "+" in s[10:]:
            s = s.split("+")[0].strip()
        try:
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
            local = dt.astimezone(ISRAEL_TZ)
            return local.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    print("Читаем данные из базы данных...")
    database.init_db()

    rows = database.get_latest_prices(limit=500_000)

    if not rows:
        print("База данных пуста!")
        print("Сначала запустите: python download_all.py")
        raise SystemExit(1)

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
        for chain in item["ch"]:
            chain_counts[chain] += 1

    chains_found = [chain for chain, _ in chain_counts.most_common()]
    in_multiple = sum(1 for item in catalog if len(item["ch"]) >= 2)

    print(f"  Уникальных штрихкодов: {len(catalog):,}")
    print(f"  Товаров в 2+ сетях:    {in_multiple:,}")
    print(f"  Сети: {', '.join(chains_found)}")

    stats = database.get_db_stats()
    last_update_utc = stats.get("last_update") if stats else None
    last_update = to_israel_local(last_update_utc)

    data = json.dumps(catalog, ensure_ascii=False)

    with open("data.js", "w", encoding="utf-8") as f:
        f.write("const CATALOG = ")
        f.write(data)
        f.write(";\n")
        f.write("const CATALOG_UPDATED = ")
        f.write(json.dumps(str(last_update), ensure_ascii=False))
        f.write(";\n")

    print(f"\n✓ Создан data.js ({len(catalog):,} товаров)")
    print(f"✓ CATALOG_UPDATED = {last_update} (Asia/Jerusalem)")
    if last_update_utc:
        print(f"  (из БД UTC: {last_update_utc})")
    print("✓ HTML больше не генерируется: интерфейс находится во frontend-репозитории.")


if __name__ == "__main__":
    main()
