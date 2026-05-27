from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.utils import FileTypesFilters
import os, gzip, shutil

os.makedirs("dumps", exist_ok=True)

# Цепочки которые используют HTTP (не FTP) — скорее всего работают
CHAINS_TO_TEST = [
    ("VICTORY", ScraperFactory.VICTORY),
    ("YOHANANOF", ScraperFactory.YOHANANOF),
    ("OSHER_AD", ScraperFactory.OSHER_AD),
    ("TIV_TAAM", ScraperFactory.TIV_TAAM),
    ("HAZI_HINAM", ScraperFactory.HAZI_HINAM),
]

print("Тестируем цепочки магазинов...")
print("=" * 55)

results = []

for name, factory in CHAINS_TO_TEST:
    print(f"\n>>> {name}")
    folder = f"dumps\\{name.replace('_','')}"
    os.makedirs(folder, exist_ok=True)

    try:
        scraper = factory.value()
        scraper.scrape(limit=1, files_types=[FileTypesFilters.PRICE_FULL_FILE.value])

        # Ищем скачанные файлы
        all_files = []
        for root, dirs, files in os.walk("dumps"):
            for f in files:
                if name.replace("_", "").lower() in root.lower() or any(
                    x in root for x in [name, name.lower()]
                ):
                    all_files.append(os.path.join(root, f))

        # Ищем папку библиотеки
        best_folder = None
        for d in os.listdir("dumps"):
            dpath = os.path.join("dumps", d)
            if os.path.isdir(dpath) and d != "Shufersal" and d != "RamiLevy":
                files_in = os.listdir(dpath)
                if files_in:
                    best_folder = dpath
                    break

        if best_folder:
            files = os.listdir(best_folder)
            total_size = sum(
                os.path.getsize(os.path.join(best_folder, f)) for f in files
            )
            print(
                f"  Папка: {best_folder}, файлов: {len(files)}, размер: {total_size:,} байт"
            )
            if total_size > 50000:
                print(f"  ✓ РАБОТАЕТ! Большие файлы — вероятно полный каталог")
                results.append((name, best_folder, total_size, "OK"))
            else:
                print(f"  ? Маленькие файлы ({total_size} байт) — возможно неполные")
                results.append((name, best_folder, total_size, "SMALL"))
        else:
            print(f"  ✗ Файлы не найдены")
            results.append((name, None, 0, "EMPTY"))

    except Exception as e:
        err = str(e)[:80]
        print(f"  ✗ Ошибка: {err}")
        results.append((name, None, 0, f"ERROR: {err}"))

print("\n" + "=" * 55)
print("ИТОГ:")
for name, folder, size, status in results:
    icon = "✓" if status == "OK" else "?" if status == "SMALL" else "✗"
    print(f"  {icon} {name}: {status} ({size:,} байт)")
