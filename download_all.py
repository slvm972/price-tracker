"""
download_all.py — скачивает XML-файлы и сохраняет цены в SQLite.

Исправления v3:
  - Все пути абсолютные (os.path.abspath) — устраняет рассогласование путей
  - После скачивания выводит список файлов в папке для диагностики
  - process_folder_to_db обрабатывает файлы без учёта регистра расширения
"""

import os, sys, gzip, shutil, time
import xml.etree.ElementTree as ET
import database

# ── Абсолютный путь к корневой папке проекта ─────────────────────
# Всегда D:\price-tracker независимо от того, откуда запущен скрипт
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DUMPS    = os.path.join(BASE_DIR, "dumps")
os.makedirs(DUMPS, exist_ok=True)

MIN_SIZE = 200_000   # >200 КБ = полный каталог (не обновление)
LIMIT    = 5

print(f"Рабочая папка:  {BASE_DIR}")
print(f"Папка с данными: {DUMPS}")

# ── Список сетей ──────────────────────────────────────────────────
# Импортируем ScraperFactory после того как убедились что скрипт запущен правильно
try:
    from il_supermarket_scarper import ScraperFactory
except ImportError:
    print("ОШИБКА: библиотека il_supermarket_scarper не установлена")
    sys.exit(1)

CHAINS = [
    ("Victory",     ScraperFactory.VICTORY_NEW_SOURCE,              "VictoryNewSource"),
    ("Shufersal",   ScraperFactory.SHUFERSAL,                       "Shufersal"),
    ("HaziHinam",   ScraperFactory.HAZI_HINAM,                      "HaziHinam"),
    ("YaynoeBitan", ScraperFactory.YAYNO_BITAN_AND_CARREFOUR,       "YaynotBitanAndCarrefour"),
    ("Keshet",      ScraperFactory.KESHET,                          "Keshet"),
]


# ── Разархивирование ──────────────────────────────────────────────

def try_decompress(src, dst):
    """Пробует распаковать файл как gzip. Возвращает True если успешно."""
    try:
        with gzip.open(src, "rb") as fi:
            content = fi.read(4)
        if not content:
            return False
        with gzip.open(src, "rb") as fi, open(dst, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        return True
    except Exception:
        return False


def rename_if_xml(path):
    """Если файл начинается с '<' — это XML без расширения, переименуем."""
    try:
        with open(path, "rb") as f:
            start = f.read(10).lstrip()
        if start.startswith(b"<") and not path.endswith(".xml"):
            os.rename(path, path + ".xml")
            return path + ".xml"
    except Exception:
        pass
    return path


def decompress_folder(folder):
    """
    Распаковывает архивы в папке. Три случая:
      .gz      → без .gz  (+ проверяем что это xml)
      без расш → пробуем как gzip → .xml
      Victory: библиотека сама распаковывает, но может оставить файл без расш.
    """
    if not os.path.isdir(folder):
        return
    for f in list(os.listdir(folder)):
        path = os.path.join(folder, f)
        if not os.path.isfile(path):
            continue
        if f.lower().endswith(".gz"):
            dst = path[:-3]
            if not os.path.exists(dst):
                if try_decompress(path, dst):
                    os.remove(path)
                    rename_if_xml(dst)
                # else: оставляем как есть
            else:
                os.remove(path)
        elif "." not in f:
            dst = path + ".xml"
            if os.path.exists(dst):
                continue           # уже распаковано библиотекой
            if try_decompress(path, dst):
                os.remove(path)
            else:
                rename_if_xml(path)


# ── Поиск папки по нечёткому совпадению ──────────────────────────

def find_folder(hint):
    """Ищет папку в DUMPS по нечёткому совпадению имени."""
    key = hint.lower().replace(" ", "").replace("_", "").replace("-", "")
    best = None
    for d in os.listdir(DUMPS):
        if d.lower() == "status":
            continue
        fp = os.path.join(DUMPS, d)
        if not os.path.isdir(fp):
            continue
        dk = d.lower().replace(" ", "").replace("_", "").replace("-", "")
        if key == dk:
            return fp           # точное совпадение — сразу возвращаем
        if key[:8] in dk or dk[:8] in key:
            best = fp
    return best


# ── Подсчёт XML-файлов ────────────────────────────────────────────

def count_xml_files(folder):
    """
    Считает XML-файлы в папке.
    Возвращает (large, small) — полные каталоги и маленькие обновления.
    """
    if not os.path.isdir(folder):
        return 0, 0
    large = small = 0
    for f in os.listdir(folder):
        if not f.lower().endswith(".xml"):
            continue
        try:
            size = os.path.getsize(os.path.join(folder, f))
        except Exception:
            continue
        if size >= MIN_SIZE:
            large += 1
        else:
            small += 1
    return large, small


def has_fresh_data(folder, max_age_hours=24):
    """True если в папке есть крупный XML-файл моложе max_age_hours часов."""
    large, _ = count_xml_files(folder)
    if large == 0:
        return False
    try:
        newest = max(
            os.path.getmtime(os.path.join(folder, f))
            for f in os.listdir(folder)
            if f.lower().endswith(".xml")
        )
        return (time.time() - newest) / 3600 < max_age_hours
    except Exception:
        return False


# ── Очистка ───────────────────────────────────────────────────────

def clear_folder_files(folder):
    """Удаляет все файлы в папке (не рекурсивно)."""
    if not os.path.isdir(folder):
        return
    removed = 0
    for f in os.listdir(folder):
        fp = os.path.join(folder, f)
        if os.path.isfile(fp):
            try:
                os.remove(fp)
                removed += 1
            except Exception as e:
                print(f"    Не удалось удалить {f}: {e}")
    if removed:
        print(f"    Очищено {removed} старых файлов")


def clear_status_for_chain(chain_hint):
    """Удаляет записи статуса для данной сети из dumps/status/."""
    status_dir = os.path.join(DUMPS, "status")
    if not os.path.isdir(status_dir):
        return
    key = chain_hint.lower().replace(" ", "").replace("_", "").replace("-", "")
    for f in list(os.listdir(status_dir)):
        fk = f.lower().replace(" ", "").replace("_", "").replace("-", "")
        if key[:6] in fk or fk[:6] in key:
            try:
                os.remove(os.path.join(status_dir, f))
            except Exception:
                pass


# ── Диагностика папки ─────────────────────────────────────────────

def print_folder_contents(folder, label=""):
    """Выводит список XML-файлов в папке для диагностики."""
    if not os.path.isdir(folder):
        print(f"    [{label}] папка не существует: {folder}")
        return
    files = sorted(os.listdir(folder))
    xml_files = [f for f in files if f.lower().endswith(".xml")]
    other = [f for f in files if not f.lower().endswith(".xml") and f != "status"]
    print(f"    [{label}] папка: {folder}")
    print(f"    XML файлов: {len(xml_files)}, прочих: {len(other)}")
    for f in xml_files[:10]:   # показываем первые 10
        size = os.path.getsize(os.path.join(folder, f))
        print(f"      {f}  ({size:,} байт)")
    if len(xml_files) > 10:
        print(f"      ... и ещё {len(xml_files) - 10} файлов")
    for f in other[:5]:
        print(f"      (прочее) {f}")


# ── Парсинг XML ───────────────────────────────────────────────────

def parse_xml_to_items(xml_path):
    """Читает один XML-файл, возвращает (store_code, [items])."""
    fname = os.path.basename(xml_path)
    if any(kw in fname for kw in ("Promo", "NULL", "promo", "null")):
        return None, []
    try:
        size = os.path.getsize(xml_path)
    except Exception:
        return None, []
    if size < 500:
        return None, []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        print(f"    Ошибка парсинга {fname}: {e}")
        return None, []

    store_code = (
        root.findtext("StoreId") or
        root.findtext("BranchId") or
        root.findtext("SubChainID") or "000"
    )

    items = []
    for item in root.findall(".//Item"):
        barcode = (item.findtext("ItemCode") or "").strip()
        name    = (item.findtext("ItemName") or "").strip()
        price   = (item.findtext("ItemPrice") or "").strip()
        brand   = (item.findtext("ManufacturerName") or "").strip()
        unit    = (item.findtext("UnitOfMeasure") or "").strip()
        qty     = (item.findtext("Quantity") or item.findtext("UnitQty") or "").strip()

        if not barcode or not name or not price:
            continue
        try:
            price_f = round(float(price), 2)
            if price_f <= 0:
                continue
        except ValueError:
            continue

        size_str = f"{qty} {unit}".strip() if (qty or unit) else ""
        items.append({
            "barcode": barcode,
            "name":    name,
            "price":   price_f,
            "brand":   brand,
            "size":    size_str,
        })

    return store_code, items


def process_folder_to_db(retailer_name, folder, recorded_at):
    """Читает все Price XML из папки и пишет в базу данных."""
    if not os.path.isdir(folder):
        print(f"    Папка не найдена: {folder}")
        return 0

    # Берём все .xml (регистр не важен), фильтруем промо и NULL
    all_files = os.listdir(folder)
    xml_files = [
        f for f in all_files
        if f.lower().endswith(".xml")
        and "promo" not in f.lower()
        and "null"  not in f.lower()
    ]

    if not xml_files:
        # Если нет Price-файлов — берём все xml (может быть другая структура)
        xml_files = [f for f in all_files if f.lower().endswith(".xml")]

    total_saved = 0
    for fname in sorted(xml_files):
        path = os.path.join(folder, fname)
        store_code, items = parse_xml_to_items(path)
        if not items:
            continue
        saved = database.save_items_batch(retailer_name, store_code, items, recorded_at)
        total_saved += saved
        print(f"    {fname}: {len(items):,} товаров → {saved:,} в БД")

    return total_saved


# ── Основной цикл ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("  Скачивание и сохранение цен в базу данных")
print(f"  {time.strftime('%d.%m.%Y %H:%M')}")
print("=" * 60)

print("\n[1/3] Инициализация базы данных...")
database.init_db()

recorded_at = time.strftime("%Y-%m-%d %H:%M:%S")

print(f"\n[2/3] Скачивание и парсинг...")
results = []

for name, factory, folder_hint in CHAINS:
    print(f"\n▶ {name}...")
    t0 = time.time()

    # Ищем или создаём папку с абсолютным путём
    folder = find_folder(folder_hint)
    if not folder:
        folder = os.path.join(DUMPS, folder_hint)
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)

    # Если данные свежие — только пишем в БД
    if has_fresh_data(folder):
        large, small = count_xml_files(folder)
        print(f"  Данные свежие ({large} полных + {small} обновлений) — пишем в БД...")
        saved = process_folder_to_db(name, folder, recorded_at)
        results.append((name, large, small, "CACHED", saved))
        continue

    # Чистим старые файлы и статус
    clear_folder_files(folder)
    clear_status_for_chain(folder_hint)

    # Скачиваем
    ok, err = False, ""
    old_cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)        # убеждаемся что рабочая папка правильная
        factory.value().scrape(limit=LIMIT)
        ok = True
    except Exception as e:
        err = str(e)
        if "425" in err or "ftp" in err.lower():
            err = "FTP заблокирован"
        else:
            err = err[:80]
    finally:
        os.chdir(old_cwd)

    # Распаковываем (на случай если библиотека оставила .gz или файлы без расш.)
    decompress_folder(folder)

    # Если папка всё ещё пустая — ищем альтернативное расположение
    large, small = count_xml_files(folder)
    if large + small == 0:
        # Диагностика: что вообще есть в dumps?
        print(f"  ⚠ XML не найдены, диагностика:")
        print_folder_contents(folder, "ожидаемая папка")
        alt = find_folder(folder_hint)
        if alt and os.path.abspath(alt) != folder:
            print_folder_contents(alt, "найденная альтернатива")
            decompress_folder(alt)
            large, small = count_xml_files(alt)
            if large + small > 0:
                folder = os.path.abspath(alt)
                print(f"  → Переключились на: {folder}")

    elapsed = round(time.time() - t0, 1)

    if not ok and large + small == 0:
        print(f"  ✗ {err} ({elapsed}с)")
        results.append((name, 0, 0, f"ERR: {err}", 0))
        continue

    # Диагностика — всегда показываем что нашли
    print_folder_contents(folder, f"после скачивания")

    print(f"  Сохраняем в базу данных...")
    saved = process_folder_to_db(name, folder, recorded_at)

    status = "OK" if large > 0 else "SMALL"
    icon = "✓" if large > 0 else "⚠"
    print(f"  {icon} {large} полных + {small} обновлений | {saved:,} записей ({elapsed}с)")
    results.append((name, large, small, status, saved))

# ── Итог ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ИТОГ:")
print("=" * 60)
for name, large, small, status, saved in results:
    icon = "✓" if status in ("OK", "CACHED") else "⚠" if status == "SMALL" else "✗"
    print(f"  {icon} {name:<15} {saved:>8,} записей в БД")

stats = database.get_db_stats()
print(f"\nБаза данных:")
print(f"  Уникальных товаров: {stats['products']:,}")
print(f"  Магазинов:          {stats['stores']:,}")
print(f"  Записей цен:        {stats['prices']:,}")
print(f"  Последнее обновление: {stats['last_update']}")
print(f"\n→ Следующий шаг: python make_viewer.py")
