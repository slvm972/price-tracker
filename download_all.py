"""
download_all.py — скачивает XML-файлы и сохраняет цены в SQLite.

Исправления v3:
  - Все пути абсолютные (os.path.abspath) — устраняет рассогласование путей
  - После скачивания выводит список файлов в папке для диагностики
  - process_folder_to_db обрабатывает файлы без учёта регистра расширения
"""

import argparse
import asyncio
import os, sys, gzip, shutil, time, json
import xml.etree.ElementTree as ET
import database
from price_utils import parse_xml_to_items

# ── Абсолютный путь к корневой папке проекта ─────────────────────
# Всегда D:\price-tracker независимо от того, откуда запущен скрипт
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DUMPS = os.path.join(BASE_DIR, "dumps")
os.makedirs(DUMPS, exist_ok=True)
ALERTS = os.path.join(BASE_DIR, "alerts")
os.makedirs(ALERTS, exist_ok=True)
ALERT_FILE = os.path.join(ALERTS, "new_data.log")
NONEMPTY_FILE = os.path.join(ALERTS, "nonempty_files.log")

MIN_SIZE = 200_000  # >200 КБ = полный каталог (не обновление)
LIMIT = 5


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download supermarket price XML files and save them into SQLite."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip download and process only local dumps/ XML files.",
    )
    parser.add_argument(
        "--force-scrape",
        action="store_true",
        help="Attempt scraping even if local data is fresh.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=LIMIT,
        help="Maximum number of files to download from scraper when not offline.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all active scrapers supported by il_supermarket_scarper.",
    )
    parser.add_argument(
        "--chains",
        type=str,
        default=None,
        help="Comma-separated list of scraper names to run. Use --list-chains to see names.",
    )
    parser.add_argument(
        "--list-chains",
        action="store_true",
        help="Print all available scraper names and exit.",
    )
    return parser.parse_args()


async def run_scraper(scraper, limit):
    async for _ in scraper.scrape(limit=limit):
        pass


args = parse_args()

print(f"Рабочая папка:  {BASE_DIR}")
print(f"Папка с данными: {DUMPS}")
if args.offline:
    print(
        "Режим: OFFLINE — загрузка данных пропущена, обрабатываются только локальные файлы."
    )
elif args.force_scrape:
    print(
        "Режим: FORCE SCRAPE — будет попытка загрузить данные даже при свежих локальных файлах."
    )

# ── Список сетей ──────────────────────────────────────────────────
# Импортируем ScraperFactory после того как убедились что скрипт запущен правильно
try:
    from il_supermarket_scarper import ScraperFactory
    from il_supermarket_scarper.utils import DiskFileOutput
except Exception as e:
    import traceback

    print("REAL IMPORT ERROR:")
    traceback.print_exc()
    venv_python = os.path.join(BASE_DIR, ".venv", "bin", "python")
    print("\nЕсли вы не активировали виртуальное окружение, запустите:")
    print(f"  {venv_python} {os.path.basename(__file__)}")
    print("или активируйте .venv и снова запустите python download_all.py")
    input("\nENTER...")
    sys.exit(1)

# Built-in fallback default chains (small stable set)
BUILTIN_DEFAULT_CHAINS = [
    "SHUFERSAL",
    "HAZI_HINAM",
    "YAYNO_BITAN_AND_CARREFOUR",
    "KESHET",
]


def load_default_chains():
    """Load default chains from config/default_chains.json if present,
    otherwise return the built-in fallback list."""
    cfg_path = os.path.join(BASE_DIR, "config", "default_chains.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
            print(
                f"  (warning) {cfg_path} is not a non-empty list — using builtin defaults"
            )
        except Exception as e:
            print(
                f"  (warning) failed to load {cfg_path}: {e} — using builtin defaults"
            )
    return BUILTIN_DEFAULT_CHAINS


DEFAULT_CHAINS = load_default_chains()


def normalize_chain_name(name):
    return "".join(ch.upper() for ch in name if ch.isalnum())


def get_chain_enum(name):
    normalized = normalize_chain_name(name)
    for member in ScraperFactory:
        if normalize_chain_name(member.name) == normalized:
            return member
        if normalize_chain_name(member.value.__name__) == normalized:
            return member
    return None


def list_available_chains():
    names = [member.name for member in ScraperFactory]
    print("Available chains:")
    for n in names:
        print(f"  - {n}")
    print("\nUse --chains name1,name2 or --all to run multiple chains.")


def build_chain_list(args):
    if args.list_chains:
        list_available_chains()
        sys.exit(0)

    if args.all:
        return [
            (member.value.__name__, member, member.value.__name__)
            for member in ScraperFactory.all_active()
        ]

    if args.chains:
        selected = []
        for name in args.chains.split(","):
            name = name.strip()
            if not name:
                continue
            enum = get_chain_enum(name)
            if enum is None:
                raise ValueError(
                    f"Unknown chain '{name}'. Use --list-chains to see available names."
                )
            selected.append((enum.value.__name__, enum, enum.value.__name__))
        return selected
    # Use DEFAULT_CHAINS to build a list of enums; skip unknowns with a warning.
    selected = []
    for name in DEFAULT_CHAINS:
        enum = get_chain_enum(name)
        if enum is None:
            print(f"  (warning) default chain not found in ScraperFactory: {name}")
            continue
        selected.append((enum.value.__name__, enum, enum.value.__name__))
    return selected


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
                continue  # уже распаковано библиотекой
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
            return fp  # точное совпадение — сразу возвращаем
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
    for f in xml_files[:10]:  # показываем первые 10
        size = os.path.getsize(os.path.join(folder, f))
        print(f"      {f}  ({size:,} байт)")
    if len(xml_files) > 10:
        print(f"      ... и ещё {len(xml_files) - 10} файлов")
    for f in other[:5]:
        print(f"      (прочее) {f}")


# ── Парсинг XML ───────────────────────────────────────────────────

# parse_xml_to_items moved to price_utils.py for easier testing


def process_folder_to_db(retailer_name, folder, recorded_at):
    """Читает все Price XML из папки и пишет в базу данных."""
    if not os.path.isdir(folder):
        print(f"    Папка не найдена: {folder}")
        return 0

    # Берём все .xml (регистр не важен), фильтруем промо и NULL
    all_files = os.listdir(folder)
    xml_files = [
        f
        for f in all_files
        if f.lower().endswith(".xml")
        and "promo" not in f.lower()
        and "null" not in f.lower()
    ]

    if not xml_files:
        # Если нет Price-файлов — берём все xml (может быть другая структура)
        xml_files = [f for f in all_files if f.lower().endswith(".xml")]

    total_saved = 0
    parsed_total = 0
    for fname in sorted(xml_files):
        path = os.path.join(folder, fname)
        store_code, items = parse_xml_to_items(path)
        # Log non-empty XML files even if DB save results in 0
        try:
            if items and len(items) > 0:
                with open(NONEMPTY_FILE, "a", encoding="utf-8") as nf:
                    nf.write(
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{retailer_name}\t{fname}\t{len(items)}\n"
                    )
        except Exception:
            pass
        if not items:
            continue
        parsed_total += len(items)
        saved = database.save_items_batch(retailer_name, store_code, items, recorded_at)
        total_saved += saved
        print(f"    {fname}: {len(items):,} товаров → {saved:,} в БД")

    return total_saved, parsed_total


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

chaingroups = build_chain_list(args)

for name, factory, folder_hint in chaingroups:
    print(f"\n▶ {name}...")
    t0 = time.time()

    # Ищем или создаём папку с абсолютным путём
    folder = find_folder(folder_hint)
    if not folder:
        folder = os.path.join(DUMPS, folder_hint)
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)

    # Если данные свежие — только пишем в БД, но если указан force_scrape, всё равно скачиваем.
    if has_fresh_data(folder) and not args.force_scrape:
        large, small = count_xml_files(folder)
        print(f"  Данные свежие ({large} полных + {small} обновлений) — пишем в БД...")
        saved, parsed = process_folder_to_db(name, folder, recorded_at)
        results.append((name, large, small, "CACHED", saved, parsed))
        continue

    if args.offline:
        print(
            "  OFFLINE: пропускаем скачивание и обрабатываем только локальные данные."
        )
        saved, parsed = process_folder_to_db(name, folder, recorded_at)
        status = "OFFLINE" if count_xml_files(folder)[0] > 0 else "EMPTY"
        results.append((name, *count_xml_files(folder), status, saved, parsed))
        continue

    # ВРЕМЕННО отключено для отладки
    # clear_folder_files(folder)
    # clear_status_for_chain(folder_hint)

    # Скачиваем
    ok, err = False, ""
    old_cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)  # убеждаемся что рабочая папка правильная
        file_output = DiskFileOutput(storage_path=folder)
        scraper = factory.value(file_output=file_output)
        asyncio.run(run_scraper(scraper, args.limit))
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
        results.append((name, 0, 0, f"ERR: {err}", 0, 0))
        continue

    # Диагностика — всегда показываем что нашли
    print_folder_contents(folder, f"после скачивания")

    print(f"  Сохраняем в базу данных...")
    saved, parsed = process_folder_to_db(name, folder, recorded_at)

    status = "OK" if large > 0 else "SMALL"
    icon = "✓" if large > 0 else "⚠"
    print(
        f"  {icon} {large} полных + {small} обновлений | {parsed:,} распознано → {saved:,} записей ({elapsed}с)"
    )
    results.append((name, large, small, status, saved, parsed))
    # Оповещение: если появились новые записи — логируем в alerts/new_data.log
    try:
        if saved and saved > 0:
            with open(ALERT_FILE, "a", encoding="utf-8") as af:
                af.write(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{saved}\t{folder}\n"
                )
            print(
                f"  → Новые записи: {saved} для {name} (записано в alerts/new_data.log)"
            )
    except Exception:
        pass

# ── Итог ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ИТОГ:")
print("=" * 60)
for name, large, small, status, saved, parsed in results:
    icon = "✓" if status in ("OK", "CACHED") else "⚠" if status == "SMALL" else "✗"
    print(f"  {icon} {name:<15} {saved:>8,} записей в БД  | {parsed:,} распозн.")

stats = database.get_db_stats()
print(f"\nБаза данных:")
print(f"  Уникальных товаров: {stats['products']:,}")
print(f"  Магазинов:          {stats['stores']:,}")
print(f"  Записей цен:        {stats['prices']:,}")
print(f"  Последнее обновление: {stats['last_update']}")
print(f"\n→ Следующий шаг: python make_viewer.py")
