from il_supermarket_scarper import ScraperFactory
import os, gzip, shutil, inspect, re

SAVE_FOLDER = "dumps\\Victory"
os.makedirs(SAVE_FOLDER, exist_ok=True)


def clear_folder(folder):
    for f in os.listdir(folder):
        os.remove(os.path.join(folder, f))
        print(f"  Удалён: {f}")


def extract_and_show(folder):
    for f in list(os.listdir(folder)):
        path = os.path.join(folder, f)
        if f.endswith(".gz"):
            xml = path[:-3]
            try:
                with gzip.open(path, "rb") as fi, open(xml, "wb") as fo:
                    shutil.copyfileobj(fi, fo)
                os.remove(path)
            except Exception as e:
                pass
    full = 0
    print(f"\nФайлы в {folder}:")
    for f in sorted(os.listdir(folder)):
        path = os.path.join(folder, f)
        size = os.path.getsize(path)
        if "Full" in f:
            print(f"  [ПОЛНЫЙ] {f}: {size:,} байт")
            full += 1
        elif "Promo" in f:
            print(f"  [акции]  {f}: {size:,} байт")
        else:
            print(f"  [другой] {f}: {size:,} байт")
    return full


# ── Шаг 1: читаем исходники библиотеки ────────────────────────────
print("=" * 60)
print("Шаг 1: Читаем исходный код Victory и Victory_new_source")
print("=" * 60)

for name, factory in [
    ("VICTORY", ScraperFactory.VICTORY),
    ("VICTORY_NEW_SOURCE", ScraperFactory.VICTORY_NEW_SOURCE),
]:
    try:
        obj = factory.value()
        src = inspect.getfile(type(obj))
        print(f"\n{name} → {src}")
        with open(src, encoding="utf-8", errors="ignore") as f:
            code = f.read()
        urls = re.findall(r'https?://[^\s\'"\\)]+', code)
        for u in set(urls):
            print(f"  URL: {u}")
        # Ищем параметры инициализации
        for line in code.splitlines():
            if any(k in line for k in ["url", "ftp", "login", "password", "user"]):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    print(f"  КОД: {stripped[:120]}")
    except Exception as e:
        print(f"  Ошибка чтения: {e}")

# ── Шаг 2: пробуем VICTORY_NEW_SOURCE ─────────────────────────────
print("\n" + "=" * 60)
print("Шаг 2: Пробуем VICTORY_NEW_SOURCE (другой сервер)")
print("=" * 60)

new_folder = "dumps\\VictoryNew"
os.makedirs(new_folder, exist_ok=True)

try:
    scraper = ScraperFactory.VICTORY_NEW_SOURCE.value()
    print(f"  URL: {getattr(scraper, 'url', 'неизвестен')}")
    scraper.scrape(limit=3)
    files = os.listdir(new_folder)
    if files:
        print(f"  Скачано файлов: {len(files)}")
        for f in files:
            size = os.path.getsize(os.path.join(new_folder, f))
            print(f"    {f}: {size:,} байт")
    else:
        # Файлы могут быть в другой папке — проверим dumps целиком
        for d in os.listdir("dumps"):
            dp = os.path.join("dumps", d)
            if os.path.isdir(dp) and d not in (
                "Shufersal",
                "Victory",
                "RamiLevy",
                "HAZIHINAM",
                "OSHERAD",
                "TIVTAAM",
                "YOHANANOF",
                "status",
            ):
                flist = os.listdir(dp)
                if flist:
                    print(f"  Найдено в dumps\\{d}: {len(flist)} файлов")
                    for f in flist:
                        size = os.path.getsize(os.path.join(dp, f))
                        print(f"    {f}: {size:,} байт")
except Exception as e:
    print(f"  Ошибка: {e}")

# ── Шаг 3: Victory с files_names_to_scrape ────────────────────────
print("\n" + "=" * 60)
print("Шаг 3: Victory — фильтр по имени файла (files_names_to_scrape)")
print("=" * 60)

print("Очищаем папку Victory...")
clear_folder(SAVE_FOLDER)

try:
    scraper = ScraperFactory.VICTORY.value()
    # files_names_to_scrape — список подстрок, которые должны быть в имени
    scraper.scrape(limit=10, files_names_to_scrape=["PriceFull"])
    print("OK")
except Exception as e:
    print(f"Ошибка: {e}")
    print("Пробуем без фильтра, limit=30...")
    try:
        clear_folder(SAVE_FOLDER)
        scraper = ScraperFactory.VICTORY.value()
        scraper.scrape(limit=30)
        print("OK")
    except Exception as e2:
        print(f"Ошибка: {e2}")

n = extract_and_show(SAVE_FOLDER)
if n > 0:
    print(f"\n✓ УСПЕХ! Скачано {n} полных файлов с ценами!")
    print("  Теперь запустите: python parse_prices.py")
    print(
        "  (не забудьте поменять DUMPS_FOLDER на 'dumps\\\\Victory' в parse_prices.py)"
    )
else:
    print("\n✗ PriceFull не найдены. Смотрите лог выше для диагностики.")
    print("  Возможно Victory хранит полные цены на другом сервере.")
