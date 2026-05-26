"""
database.py — SQLite-хранилище для price-tracker.

Поток данных:
    download_all.py → парсит XML → вызывает функции этого файла → SQLite
    make_viewer.py  → вызывает функции этого файла → HTML

Почему SQLite а не XML-файлы:
    - Быстрый поиск по штрихкоду, цене, сети
    - История цен (каждое скачивание добавляет новую запись)
    - Не нужно каждый раз перечитывать все XML
    - Легко анализировать через любой SQL-клиент

Схема базы данных:
    products   — уникальные товары (по штрихкоду)
    stores     — магазины / сети
    prices     — цена товара в магазине в момент времени
    promotions — акционные цены (опционально, пока не используется)
"""

import sqlite3
import os
from datetime import datetime

# Путь к файлу базы данных
DB_PATH = os.path.join(os.path.dirname(__file__), "prices.db")


def get_connection():
    """
    Возвращает соединение с базой данных.
    Вызывается каждый раз когда нужно что-то записать или прочитать.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # строки как словари: row["name"] вместо row[0]
    conn.execute("PRAGMA journal_mode=WAL")   # ускоряет запись
    conn.execute("PRAGMA synchronous=NORMAL") # баланс скорость/надёжность
    return conn


def init_db():
    """
    Создаёт таблицы если они ещё не существуют.
    Безопасно вызывать при каждом запуске — повторное создание не ломает данные.
    """
    conn = get_connection()
    with conn:
        conn.executescript("""
            -- Товары: один товар = одна строка, идентифицируется по штрихкоду
            CREATE TABLE IF NOT EXISTS products (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT    UNIQUE NOT NULL,  -- штрихкод — главный ключ сопоставления
                name    TEXT    NOT NULL,          -- название (берём из первой встреченной сети)
                brand   TEXT    DEFAULT '',
                size    TEXT    DEFAULT ''         -- объём/вес из поля UnitOfMeasure
            );

            -- Магазины/сети: Victory, Shufersal и т.д.
            -- store_code — внутренний номер магазина (StoreId из XML)
            CREATE TABLE IF NOT EXISTS stores (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                retailer   TEXT NOT NULL,  -- название сети: "Victory", "Shufersal"
                store_code TEXT NOT NULL,  -- StoreId из XML: "001", "026"
                UNIQUE(retailer, store_code)
            );

            -- Цены: каждая запись — цена конкретного товара в конкретном магазине
            -- в конкретный момент времени. Старые записи НЕ удаляются — это история.
            CREATE TABLE IF NOT EXISTS prices (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id),
                store_id   INTEGER NOT NULL REFERENCES stores(id),
                price      REAL    NOT NULL,
                recorded_at TEXT   NOT NULL  -- ISO формат: "2026-03-10 01:00:00"
            );

            -- Акции: пока таблица пустая, но структура готова для будущего
            CREATE TABLE IF NOT EXISTS promotions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                store_id    INTEGER NOT NULL REFERENCES stores(id),
                promo_price REAL    NOT NULL,
                start_date  TEXT,
                end_date    TEXT
            );

            -- Индексы для быстрого поиска
            CREATE INDEX IF NOT EXISTS idx_prices_product  ON prices(product_id);
            CREATE INDEX IF NOT EXISTS idx_prices_store    ON prices(store_id);
            CREATE INDEX IF NOT EXISTS idx_prices_recorded ON prices(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
        """)
    conn.close()
    print(f"  База данных готова: {DB_PATH}")


# ── Функции записи ────────────────────────────────────────────────

def get_or_create_product(conn, barcode, name, brand="", size=""):
    """
    Возвращает id товара по штрихкоду.
    Если товара нет — создаёт новый.
    Если товар уже есть — не трогает существующие данные.
    """
    row = conn.execute(
        "SELECT id FROM products WHERE barcode = ?", (barcode,)
    ).fetchone()

    if row:
        return row["id"]

    cur = conn.execute(
        "INSERT INTO products (barcode, name, brand, size) VALUES (?, ?, ?, ?)",
        (barcode, name, brand, size)
    )
    return cur.lastrowid


def get_or_create_store(conn, retailer, store_code):
    """
    Возвращает id магазина по паре (сеть, код магазина).
    Создаёт если нет.
    """
    row = conn.execute(
        "SELECT id FROM stores WHERE retailer = ? AND store_code = ?",
        (retailer, store_code)
    ).fetchone()

    if row:
        return row["id"]

    cur = conn.execute(
        "INSERT INTO stores (retailer, store_code) VALUES (?, ?)",
        (retailer, store_code)
    )
    return cur.lastrowid


def insert_price(conn, product_id, store_id, price, recorded_at):
    """
    Добавляет запись о цене.
    Всегда добавляет новую запись — не обновляет старую.
    Так сохраняется история изменения цен.
    """
    conn.execute(
        "INSERT INTO prices (product_id, store_id, price, recorded_at) VALUES (?, ?, ?, ?)",
        (product_id, store_id, price, recorded_at)
    )


def save_items_batch(retailer, store_code, items, recorded_at=None):
    """
    Сохраняет список товаров одного магазина одной транзакцией.

    Аргументы:
        retailer    — название сети: "Victory"
        store_code  — StoreId из XML: "001"
        items       — список словарей: [{"barcode", "name", "price", "brand", "size"}, ...]
        recorded_at — время записи (по умолчанию — сейчас)

    Одна транзакция намного быстрее чем N отдельных INSERT.
    """
    if not items:
        return 0

    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    saved = 0

    with conn:  # автоматический COMMIT или ROLLBACK
        store_id = get_or_create_store(conn, retailer, store_code)

        for item in items:
            barcode = item.get("barcode", "").strip().lstrip("0")
            name    = item.get("name", "").strip()
            price   = item.get("price")
            brand   = item.get("brand", "")
            size    = item.get("size", "")

            if not barcode or not name or price is None:
                continue

            try:
                price_f = float(price)
                if price_f <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            product_id = get_or_create_product(conn, barcode, name, brand, size)
            insert_price(conn, product_id, store_id, price_f, recorded_at)
            saved += 1

    conn.close()
    return saved


# ── Функции чтения ────────────────────────────────────────────────

def get_latest_prices(search_term="", limit=2000):
    """
    Возвращает последнюю известную цену каждого товара в каждой сети.

    Это основной запрос для HTML-viewer.
    Группировка: один товар + одна сеть = одна строка с последней ценой.

    Аргументы:
        search_term — фильтр по названию (ивритский текст, часть слова)
        limit       — максимум строк в результате
    """
    conn = get_connection()

    query = """
        SELECT
            p.barcode,
            p.name,
            p.brand,
            p.size,
            s.retailer,
            s.store_code,
            pr.price,
            pr.recorded_at
        FROM prices pr
        JOIN products p ON p.id = pr.product_id
        JOIN stores   s ON s.id = pr.store_id
        WHERE pr.id IN (
            -- Для каждой пары (товар, магазин) берём только последнюю запись
            SELECT MAX(id) FROM prices GROUP BY product_id, store_id
        )
        {}
        ORDER BY p.name, s.retailer
        LIMIT ?
    """

    if search_term:
        where = "AND p.name LIKE ?"
        rows = conn.execute(
            query.format(where),
            (f"%{search_term}%", limit)
        ).fetchall()
    else:
        rows = conn.execute(
            query.format(""),
            (limit,)
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def get_price_history(barcode, days=30):
    """
    Возвращает историю цен для одного товара за последние N дней.
    Используется для графика изменения цены.

    Аргументы:
        barcode — штрихкод товара
        days    — за сколько дней показывать историю
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            p.name,
            s.retailer,
            pr.price,
            pr.recorded_at
        FROM prices pr
        JOIN products p ON p.id = pr.product_id
        JOIN stores   s ON s.id = pr.store_id
        WHERE p.barcode = ?
          AND pr.recorded_at >= datetime('now', ? || ' days')
        ORDER BY pr.recorded_at, s.retailer
    """, (barcode.lstrip("0"), f"-{days}")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_db_stats():
    """
    Возвращает статистику базы данных.
    Полезно для отладки и мониторинга.
    """
    conn = get_connection()
    stats = {
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "stores":   conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0],
        "prices":   conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0],
        "retailers": conn.execute(
            "SELECT retailer, COUNT(DISTINCT store_code) as stores FROM stores GROUP BY retailer"
        ).fetchall(),
        "last_update": conn.execute(
            "SELECT MAX(recorded_at) FROM prices"
        ).fetchone()[0],
    }
    conn.close()
    return stats


# ── Запуск напрямую: инициализация + статистика ───────────────────

if __name__ == "__main__":
    print("Инициализация базы данных...")
    init_db()

    stats = get_db_stats()
    print(f"\nСтатистика базы:")
    print(f"  Товаров:       {stats['products']:,}")
    print(f"  Магазинов:     {stats['stores']:,}")
    print(f"  Записей цен:   {stats['prices']:,}")
    print(f"  Последнее обновление: {stats['last_update'] or 'нет данных'}")
    if stats["retailers"]:
        print(f"\n  Сети:")
        for r in stats["retailers"]:
            print(f"    {r['retailer']:<20} {r['stores']} магазинов")
