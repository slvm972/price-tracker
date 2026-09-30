"""
database.py — SQLite-хранилище для price-tracker.

Поток данных:
    download_all.py → парсит XML → вызывает функции этого файла → SQLite
    make_viewer.py  → вызывает функции этого файла → HTML

Почеместо
"""
# Diff format test

database.py — SQLite-хранилище для price-tracker.

Поток данных:
    download_all.py → парсит XML → вызывает функции этого файла → SQLite
    make_viewer.py  → вызывает функции этого файла → HTML

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "prices.db")

# Минимальная версия SQLite для оконных функций (LAG, OVER PARTITION BY)
_MIN_SQLITE_VERSION = (3, 25, 0)


def get_connection():
    """
    Возвращает соединение с базой данных.
    Выбрасывает RuntimeError если версия SQLite слишком старая.
    """
    ver = sqlite3.sqlite_version_info
    if ver < _MIN_SQLITE_VERSION:
        need = ".".join(str(x) for x in _MIN_SQLITE_VERSION)
        have = ".".join(str(x) for x in ver)
        raise RuntimeError(
            f"SQLite {have} слишком старый — нужен >= {need}.\n"
            "Обновите Python (3.12+) или пересоберите SQLite: https://www.sqlite.org/download.html"
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """
    Создаёт таблицы и индексы если они ещё не существуют.
    Безопасно вызывать при каждом запуске.
    """
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT    UNIQUE NOT NULL,
                name    TEXT    NOT NULL,
                brand   TEXT    DEFAULT '',
                size    TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS stores (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                retailer   TEXT NOT NULL,
                store_code TEXT NOT NULL,
                UNIQUE(retailer, store_code)
            );

            CREATE TABLE IF NOT EXISTS prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                store_id    INTEGER NOT NULL REFERENCES stores(id),
                price       REAL    NOT NULL,
                recorded_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS promotions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                store_id    INTEGER NOT NULL REFERENCES stores(id),
                promo_price REAL    NOT NULL,
                start_date  TEXT,
                end_date    TEXT
            );

            -- Индексы для быстрого поиска
            CREATE INDEX IF NOT EXISTS idx_prices_product   ON prices(product_id);
            CREATE INDEX IF NOT EXISTS idx_prices_store     ON prices(store_id);
            CREATE INDEX IF NOT EXISTS idx_prices_recorded  ON prices(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
            -- Для батч-кэша (load_last_price_cache)
            CREATE INDEX IF NOT EXISTS idx_prices_store_product    ON prices(store_id, product_id);
            CREATE INDEX IF NOT EXISTS idx_prices_store_product_id ON prices(store_id, product_id, id);
            -- Для основного CTE-запроса get_latest_prices (этап 2: составной индекс)
            CREATE INDEX IF NOT EXISTS idx_prices_pst ON prices(product_id, store_id, recorded_at);
        """)
    conn.close()
    print(f"  База данных готова: {DB_PATH}")


# ── Функции записи ────────────────────────────────────────────────


def get_or_create_store(conn, retailer, store_code):
    row = conn.execute(
        "SELECT id FROM stores WHERE retailer = ? AND store_code = ?",
        (retailer, store_code),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO stores (retailer, store_code) VALUES (?, ?)",
        (retailer, store_code),
    )
    return cur.lastrowid


def _load_last_price_cache(conn, store_id, product_ids):
    """Загружает последние цены для списка товаров одним запросом."""
    if not product_ids:
        return {}
    placeholders = ",".join("?" for _ in product_ids)
    sql = f"""
        SELECT p.product_id, p.price
        FROM prices p
        JOIN (
            SELECT product_id, MAX(id) AS id
            FROM prices
            WHERE store_id = ?
              AND product_id IN ({placeholders})
            GROUP BY product_id
        ) latest ON latest.id = p.id
    """
    rows = conn.execute(sql, [store_id] + product_ids).fetchall()
    return {(row["product_id"], store_id): float(row["price"]) for row in rows}


def _batch_get_or_create_products(conn, items):
    """
    Пакетный поиск/создание товаров.
    Один SELECT + один executemany вместо N отдельных запросов.
    Возвращает список product_id в том же порядке что items.
    """
    if not items:
        return []

    barcodes = [item.get("barcode", "").strip().lstrip("0") for item in items]
    unique_barcodes = list(dict.fromkeys(barcodes))

    placeholders = ",".join("?" for _ in unique_barcodes)
    existing = conn.execute(
        f"SELECT barcode, id FROM products WHERE barcode IN ({placeholders})",
        unique_barcodes,
    ).fetchall()
    existing_map = {row["barcode"]: row["id"] for row in existing}

    to_insert = []
    seen = set()
    for item in items:
        barcode = item.get("barcode", "").strip().lstrip("0")
        if barcode not in existing_map and barcode not in seen:
            seen.add(barcode)
            to_insert.append((
                barcode,
                item.get("name", "").strip(),
                item.get("brand", ""),
                item.get("size", ""),
            ))

    if to_insert:
        conn.executemany(
            "INSERT OR IGNORE INTO products (barcode, name, brand, size) VALUES (?, ?, ?, ?)",
            to_insert,
        )
        existing = conn.execute(
            f"SELECT barcode, id FROM products WHERE barcode IN ({placeholders})",
            unique_barcodes,
        ).fetchall()
        existing_map = {row["barcode"]: row["id"] for row in existing}

    return [existing_map[b] for b in barcodes]


def _insert_price(conn, product_id, store_id, price, recorded_at, cache):
    """
    Добавляет запись о цене если она изменилась.
    cache — локальный словарь {(product_id, store_id): last_price},
    передаётся явно (не глобальная переменная — этап 3).
    Возвращает True если запись была добавлена.
    """
    key = (product_id, store_id)
    price_f = float(price)

    if cache is not None:
        last = cache.get(key)
        if last is not None and last == price_f:
            return False
    else:
        row = conn.execute(
            "SELECT price FROM prices WHERE product_id = ? AND store_id = ? ORDER BY id DESC LIMIT 1",
            (product_id, store_id),
        ).fetchone()
        if row is not None:
            try:
                if float(row[0]) == price_f:
                    return False
            except Exception:
                pass

    conn.execute(
        "INSERT INTO prices (product_id, store_id, price, recorded_at) VALUES (?, ?, ?, ?)",
        (product_id, store_id, price_f, recorded_at),
    )
    if cache is not None:
        cache[key] = price_f
    return True


def save_items_batch(retailer, store_code, items, recorded_at=None):
    """
    Сохраняет список товаров одного магазина одной транзакцией.

    Аргументы:
        retailer    — название сети: "Victory"
        store_code  — StoreId из XML: "001"
        items       — список словарей: [{"barcode", "name", "price", "brand", "size"}, ...]
        recorded_at — время записи (по умолчанию — сейчас)
    """
    if not items:
        return 0

    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    saved = 0

    with conn:
        store_id = get_or_create_store(conn, retailer, store_code)

        valid_items = []
        for item in items:
            barcode = item.get("barcode", "").strip().lstrip("0")
            name = item.get("name", "").strip()
            price = item.get("price")
            if not barcode or not name or price is None:
                continue
            try:
                price_f = float(price)
                if price_f <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            valid_items.append({"item": item, "barcode": barcode, "name": name, "price": price_f})

        if valid_items:
            product_ids = _batch_get_or_create_products(conn, [v["item"] for v in valid_items])
            unique_product_ids = list(dict.fromkeys(product_ids))
            # Кэш создаётся и живёт только внутри этого вызова (этап 3)
            cache = _load_last_price_cache(conn, store_id, unique_product_ids)
            for product_id, v in zip(product_ids, valid_items):
                if _insert_price(conn, product_id, store_id, v["price"], recorded_at, cache):
                    saved += 1

    conn.close()
    return saved


def save_promos_batch(retailer, store_code, promos, recorded_at=None):
    """
    Сохраняет акционные цены из Promo*.xml (этап 5).

    promos — список словарей: [{"barcode", "name", "promo_price", "start_date", "end_date"}, ...]
    """
    if not promos:
        return 0

    conn = get_connection()
    saved = 0

    with conn:
        store_id = get_or_create_store(conn, retailer, store_code)

        valid = []
        for p in promos:
            barcode = p.get("barcode", "").strip().lstrip("0")
            name = p.get("name", "").strip()
            promo_price = p.get("promo_price")
            if not barcode or not name or promo_price is None:
                continue
            try:
                pp = float(promo_price)
                if pp <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            valid.append({"item": p, "barcode": barcode, "name": name, "promo_price": pp})

        if valid:
            product_ids = _batch_get_or_create_products(conn, [v["item"] for v in valid])
            rows = [
                (pid, store_id, v["promo_price"],
                 v["item"].get("start_date"), v["item"].get("end_date"))
                for pid, v in zip(product_ids, valid)
            ]
            conn.executemany(
                "INSERT INTO promotions (product_id, store_id, promo_price, start_date, end_date)"
                " VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            saved = len(rows)

    conn.close()
    return saved


# ── Функции чтения ────────────────────────────────────────────────


def get_latest_prices(search_term="", limit=2000):
    """
    Возвращает последнюю известную цену каждого товара в каждой сети.
    Основной запрос для HTML-viewer.
    """
    conn = get_connection()

    query = """
        WITH grouped AS (
            SELECT product_id, store_id, recorded_at, MAX(id) AS id
            FROM prices
            GROUP BY product_id, store_id, recorded_at
        ),
        with_prev AS (
            SELECT
                g.product_id,
                g.store_id,
                g.recorded_at,
                p.price,
                LAG(p.price) OVER (PARTITION BY g.product_id, g.store_id ORDER BY g.recorded_at) AS previous_price
            FROM grouped g
            JOIN prices p ON p.id = g.id
        ),
        latest AS (
            SELECT product_id, store_id, MAX(recorded_at) AS recorded_at
            FROM grouped
            GROUP BY product_id, store_id
        )
        SELECT
            prd.barcode,
            prd.name,
            prd.brand,
            prd.size,
            st.retailer,
            st.store_code,
            wp.price,
            l.recorded_at,
            wp.previous_price
        FROM latest l
        JOIN with_prev wp ON wp.product_id = l.product_id AND wp.store_id = l.store_id AND wp.recorded_at = l.recorded_at
        JOIN products prd ON prd.id = l.product_id
        JOIN stores   st  ON st.id  = l.store_id
        {}
        ORDER BY prd.name, st.retailer
        LIMIT ?
    """

    if search_term:
        rows = conn.execute(query.format("WHERE prd.name LIKE ?"), (f"%{search_term}%", limit)).fetchall()
    else:
        rows = conn.execute(query.format(""), (limit,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def get_price_history(barcode, days=30):
    """Возвращает историю цен для одного товара за последние N дней."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT p.name, s.retailer, pr.price, pr.recorded_at
        FROM prices pr
        JOIN products p ON p.id = pr.product_id
        JOIN stores   s ON s.id = pr.store_id
        WHERE p.barcode = ?
          AND pr.recorded_at >= datetime('now', ? || ' days')
        ORDER BY pr.recorded_at, s.retailer
        """,
        (barcode.lstrip("0"), f"-{days}"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_db_stats():
    """Возвращает статистику базы данных (включая версию SQLite)."""
    conn = get_connection()
    stats = {
        "sqlite_version": sqlite3.sqlite_version,
        "products":  conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "stores":    conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0],
        "prices":    conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0],
        "promotions": conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0],
        "retailers": conn.execute(
            "SELECT retailer, COUNT(DISTINCT store_code) as stores FROM stores GROUP BY retailer"
        ).fetchall(),
        "last_update": conn.execute("SELECT MAX(recorded_at) FROM prices").fetchone()[0],
    }
    conn.close()
    return stats


# ── Запуск напрямую: инициализация + статистика ───────────────────

if __name__ == "__main__":
    print("Инициализация базы данных...")
    init_db()

    stats = get_db_stats()
    print(f"\nСтатистика базы:")
    print(f"  SQLite версия:         {stats['sqlite_version']}")
    print(f"  Товаров:               {stats['products']:,}")
    print(f"  Магазинов:             {stats['stores']:,}")
    print(f"  Записей цен:           {stats['prices']:,}")
    print(f"  Акций:                 {stats['promotions']:,}")
    print(f"  Последнее обновление:  {stats['last_update'] or 'нет данных'}")
    if stats["retailers"]:
        print(f"\n  Сети:")
        for r in stats["retailers"]:
            print(f"    {r['retailer']:<20} {r['stores']} магазинов")
