import sqlite3

DB_PATH = r"D:\1\price-tracker\prices.db"

def check_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Считаем общее количество записей
    cursor.execute("SELECT COUNT(*) FROM prices")
    total_count = cursor.fetchone()[0]

    print(f"Всего товаров в базе: {total_count}\n")

    # Выводим первые 5 товаров для наглядности
    print("Пример первых 5 записей:")
    cursor.execute("SELECT chain_id, store_id, item_code, item_name, price FROM prices LIMIT 5")
    rows = cursor.fetchall()

    for row in rows:
        chain, store, code, name, price = row
        print(f"Магазин {store} | Код: {code} | {name} — {price} ₪")

    conn.close()

if __name__ == "__main__":
    check_data()