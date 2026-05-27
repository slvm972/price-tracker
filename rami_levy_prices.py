from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.utils import FileTypesFilters
import os, gzip, shutil

os.makedirs("dumps", exist_ok=True)


def find_rami_folder():
    for folder in os.listdir("dumps"):
        if "rami" in folder.lower() or "levy" in folder.lower():
            return os.path.join("dumps", folder)
    folders = [
        os.path.join("dumps", f)
        for f in os.listdir("dumps")
        if os.path.isdir(os.path.join("dumps", f))
    ]
    return max(folders, key=os.path.getmtime) if folders else None


def extract_and_show(folder):
    full = 0
    for f in os.listdir(folder):
        path = os.path.join(folder, f)
        if f.endswith(".gz"):
            xml = path.replace(".gz", "")
            if not os.path.exists(xml):
                try:
                    with gzip.open(path, "rb") as fi, open(xml, "wb") as fo:
                        shutil.copyfileobj(fi, fo)
                    print(f"  Распаковано: {f} => {os.path.getsize(xml):,} байт")
                except Exception as e:
                    print(f"  Ошибка: {e}")
    for f in sorted(os.listdir(folder)):
        path = os.path.join(folder, f)
        size = os.path.getsize(path)
        tag = (
            "ПОЛНЫЙ"
            if "Full" in f and f.endswith(".xml")
            else "частичный" if f.endswith(".xml") else "gz"
        )
        print(f"  [{tag}] {f}: {size:,} байт")
        if tag == "ПОЛНЫЙ":
            full += 1
    return full


print("=" * 55)
print("Rami Levy — скачивание полного каталога")
print("=" * 55)

for attempt, kwargs in enumerate(
    [
        {"limit": 3, "files_types": [FileTypesFilters.PRICE_FULL_FILE.value]},
        {"limit": 3},
    ],
    1,
):
    print(f"\nПопытка {attempt}...")
    try:
        ScraperFactory.RAMI_LEVY.value().scrape(**kwargs)
        print("OK")
        break
    except Exception as e:
        print(f"Ошибка: {e}")

folder = find_rami_folder()
if folder:
    print(f"\nПапка: {folder}")
    n = extract_and_show(folder)
    print(
        f"\n{'✓ Успех! ' + str(n) + ' полных файлов.' if n > 0 else '✗ Только частичные файлы.'}"
    )
else:
    print("\nПапок нет в dumps/")
