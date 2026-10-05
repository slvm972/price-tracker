import os
import sqlite3
import xml.etree.ElementTree as ET

# Пути к файлам и базе
DB_PATH = r"D:\1\price-tracker\prices.db"
DUMPS_DIR = r"D:\1\price-tracker\dumps\Shufersal"

def init_db(conn):
    """Создает таблицу prices, если ее еще нет."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chain_id TEXT,
            store_id TEXT,
            item_code TEXT,
            item_name TEXT,
            price REAL,
            update_time TEXT,
            UNIQUE(chain_id, store_id, item_code, update_time) ON CONFLICT IGNORE
        )
    """)
    conn.commit()

def parse_and_insert():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cursor = conn.cursor()

    xml_files = [f for f in os.listdir(DUMPS_DIR) if f.endswith('.xml')]
    print(f"Найдено {len(xml_files)} XML-файлов для обработки...")

    total_inserted = 0

    for file_name in xml_files:
        file_path = os.path.join(DUMPS_DIR, file_name)
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            chain_id = root.findtext('ChainID', default='')
            store_id = root.findtext('StoreID', default='')

            items = root.findall('.//Item')
            records = []

            for item in items:
                item_code = item.findtext('ItemCode', default='')
                item_name = item.findtext('ItemName', default='')
                price = item.findtext('ItemPrice', default='0.0')
                price_update_time = item.findtext('PriceUpdateTime', default='')

                if item_code and price:
                    records.append((
                        chain_id,
                        store_id,
                        item_code,
                        item_name,
                        float(price),
                        price_update_time
                    ))

            cursor.executemany("""
                INSERT OR IGNORE INTO prices (chain_id, store_id, item_code, item_name, price, update_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, records)

            conn.commit()
            print(f"Файл {file_name} успешно обработан ({len(records)} товаров).")
            total_inserted += len(records)

        except Exception as e:
            print(f"Ошибка при обработке файла {file_name}: {e}")

    conn.close()
    print(f"\nГотово! Всего записей отправлено в БД: {total_inserted}")

if __name__ == "__main__":
    parse_and_insert()