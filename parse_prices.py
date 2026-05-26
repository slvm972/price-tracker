import xml.etree.ElementTree as ET
import sys
import os
import glob

# === НАСТРОЙКИ ===
# Папка с данными Victory (VICTORY_NEW_SOURCE скачивает сюда)
DUMPS_FOLDER = "dumps\\VictoryNewSource"

# Слово для поиска по умолчанию (иврит: сок)
DEFAULT_SEARCH = "מיץ"


def parse_xml_file(xml_path, search_term=""):
    """Читает один XML файл и возвращает список найденных товаров."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"  Ошибка парсинга {os.path.basename(xml_path)}: {e}")
        return None, []

    # Читаем информацию о магазине
    store_id = (root.findtext("StoreId") or
                root.findtext("store_id") or
                root.findtext("SubChainID") or "?")
    store_name = root.findtext("StoreName") or root.findtext("ChainName") or ""

    found = []
    # XML структура может быть разной — ищем товары на всех уровнях
    items = (root.findall(".//Item") or
             root.findall(".//item") or
             root.findall(".//Product") or [])

    for item in items:
        name = (item.findtext("ItemName") or
                item.findtext("item_name") or
                item.findtext("Name") or "")
        price = (item.findtext("ItemPrice") or
                 item.findtext("item_price") or
                 item.findtext("Price") or "")
        unit = (item.findtext("UnitOfMeasure") or
                item.findtext("unit_of_measure") or
                item.findtext("Unit") or "")
        code = (item.findtext("ItemCode") or
                item.findtext("item_code") or
                item.findtext("Code") or "")
        qty = (item.findtext("Quantity") or
               item.findtext("UnitQty") or "")

        # Фильтр по поисковому слову (без учёта регистра)
        if search_term and search_term.lower() not in name.lower():
            continue

        found.append({
            "store_id": store_id,
            "store_name": store_name,
            "name": name,
            "price": price,
            "unit": unit,
            "code": code,
            "qty": qty,
            "file": os.path.basename(xml_path)
        })

    return len(items), found


def search_all_files(folder, search_term=""):
    """Ищет товары во всех XML файлах папки."""

    # Ищем все XML в папке (и во вложенных)
    xml_files = glob.glob(os.path.join(folder, "**", "*.xml"), recursive=True)
    xml_files += glob.glob(os.path.join(folder, "*.xml"))
    xml_files = list(set(xml_files))  # убираем дубли

    if not xml_files:
        print(f"\n⚠ XML файлы не найдены в папке: {folder}")
        print("  Сначала скачайте данные:")
        print("  python victory_pricefull.py")
        return

    print(f"\nНайдено XML файлов: {len(xml_files)}")
    if search_term:
        print(f"Ищем: '{search_term}'")
    else:
        print("Показываем все товары (первые 50)")
    print("-" * 60)

    all_results = []
    total_items = 0

    for xml_path in sorted(xml_files):
        fname = os.path.basename(xml_path)
        size_kb = os.path.getsize(xml_path) // 1024
        print(f"  Читаем: {fname} ({size_kb} KB)...")

        count, found = parse_xml_file(xml_path, search_term)
        if count is not None:
            total_items += count
            all_results.extend(found)
            if count > 0:
                print(f"    Товаров в файле: {count:,}, найдено совпадений: {len(found)}")

    print()
    print(f"Итого товаров в базе: {total_items:,}")
    print()

    if not all_results:
        print(f"По запросу '{search_term}' ничего не найдено.")
        print()
        print("Подсказка — попробуйте другие слова:")
        print("  חלב   — молоко")
        print("  לחם   — хлеб")
        print("  מים   — вода")
        print("  גבינה — сыр")
        print("  ביצים — яйца")
        print("  עוף   — курица")
        print("  אורז  — рис")
        return

    print(f"Найдено совпадений: {len(all_results)}")
    print("=" * 60)
    for item in all_results[:100]:  # показываем до 100 результатов
        price_str = f"{item['price']} ₪" if item['price'] else "цена неизвестна"
        unit_str = f"  {item['qty']} {item['unit']}" if item['qty'] or item['unit'] else ""
        print(f"  {item['name']}")
        print(f"    💰 {price_str}{unit_str}  |  Магазин №{item['store_id']}")
        print()

    if len(all_results) > 100:
        print(f"  ... и ещё {len(all_results) - 100} товаров.")
        print("  Для сохранения в файл добавьте > results.txt к команде")


if __name__ == "__main__":
    search = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_SEARCH
    search_all_files(DUMPS_FOLDER, search)
