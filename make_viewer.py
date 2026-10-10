"""
make_viewer.py — читает данные из SQLite и создаёт data.js
для frontend-репозитория pricetracker-interface-found.

Интерфейс price_viewer.html находится только во frontend-репозитории.
Этот скрипт больше не генерирует HTML.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import argparse
import json
import database
import catalog_filters as cf

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


def iter_latest_rows():
    """
    Потоково отдаёт последнюю цену каждого товара в каждой сети (без LIMIT).
    Запрос совпадает с database.get_latest_prices; вынесен сюда, чтобы не держать
    в памяти все строки сразу (в базе их >1,5 млн). TODO: перенести в database.py.
    """
    conn = database.get_connection()
    try:
        cur = conn.execute("""
            WITH grouped AS (
                SELECT product_id, store_id, recorded_at, MAX(id) AS id
                FROM prices
                GROUP BY product_id, store_id, recorded_at
            ),
            with_prev AS (
                SELECT g.product_id, g.store_id, g.recorded_at, p.price,
                       LAG(p.price) OVER (
                           PARTITION BY g.product_id, g.store_id ORDER BY g.recorded_at
                       ) AS previous_price
                FROM grouped g
                JOIN prices p ON p.id = g.id
            ),
            latest AS (
                SELECT product_id, store_id, MAX(recorded_at) AS recorded_at
                FROM grouped
                GROUP BY product_id, store_id
            )
            SELECT prd.barcode, prd.name, prd.brand, prd.size,
                   st.retailer, wp.price, wp.previous_price
            FROM latest l
            JOIN with_prev wp ON wp.product_id = l.product_id
                             AND wp.store_id = l.store_id
                             AND wp.recorded_at = l.recorded_at
            JOIN products prd ON prd.id = l.product_id
            JOIN stores   st  ON st.id  = l.store_id
        """)
        for row in cur:
            yield row
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Собирает data.js из SQLite.")
    parser.add_argument("--min-chains", type=int, default=2,
                        help="минимум сетей у товара (по умолчанию 2; 1 = весь каталог)")
    parser.add_argument("--min-price", type=float, default=cf.MIN_PRICE)
    parser.add_argument("--min-barcode-len", type=int, default=cf.MIN_BARCODE_LEN)
    args = parser.parse_args()

    print("Читаем данные из базы данных...")
    database.init_db()

    catalog, st = cf.build_catalog(
        iter_latest_rows(),
        min_chains=args.min_chains,
        min_price=args.min_price,
        min_barcode_len=args.min_barcode_len,
    )

    if st["rows"] == 0:
        print("База данных пуста!")
        print("Сначала запустите: python download_all.py")
        raise SystemExit(1)

    print(f"  Строк из БД (товар x сеть): {st['rows']:,}")
    print(f"  Внутренние коды сетей (не штрихкоды): {st['internal_code']:,}")
    print(f"  Отброшено: плохой штрихкод {st['bad_barcode']:,}, цена < {args.min_price} "
          f"{st['bad_price']:,}, не-товары {st['non_product']:,}")
    print(f"  Выбросы цен: {st['outlier_prices']:,} цен, "
          f"товаров убрано целиком {st['items_dropped_outliers']:,}")
    print(f"  Убрано как товары менее чем в {args.min_chains} сетях: "
          f"{st['items_dropped_min_chains']:,}")

    if not catalog:
        print("После фильтрации каталог пуст — проверьте пороги.")
        raise SystemExit(1)

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

    size_mb = len(data.encode("utf-8")) / 1_048_576
    print(f"\n✓ Создан data.js ({len(catalog):,} товаров, ~{size_mb:.1f} МБ)")
    print(f"✓ CATALOG_UPDATED = {last_update} (Asia/Jerusalem)")
    if last_update_utc:
        print(f"  (из БД UTC: {last_update_utc})")
    print("✓ HTML больше не генерируется: интерфейс находится во frontend-репозитории.")


if __name__ == "__main__":
    main()
