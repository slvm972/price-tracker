from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.utils import FileTypesFilters
import os

SAVE_FOLDER = "dumps\\Shufersal"


def clear_old_files():
    if os.path.exists(SAVE_FOLDER):
        for f in os.listdir(SAVE_FOLDER):
            if f.endswith(".xml"):
                os.remove(os.path.join(SAVE_FOLDER, f))
                print(f"  Удалён: {f}")


def check_results():
    if os.path.exists(SAVE_FOLDER):
        files = [f for f in os.listdir(SAVE_FOLDER) if f.endswith(".xml")]
        for f in files:
            size = os.path.getsize(os.path.join(SAVE_FOLDER, f))
            kind = "ПОЛНЫЙ" if "Full" in f else "обновление"
            print(f"  [{kind}] {f}: {size:,} байт")
        return len(files)
    return 0


print("Shufersal — скачивание полного каталога цен")
print("=" * 50)

# Показываем доступные типы файлов для диагностики
print("Доступные типы файлов:")
for ft in FileTypesFilters:
    print(f"  {ft.name} = {ft.value}")

print("\nОчищаем старые файлы...")
clear_old_files()

print("\nСкачиваем PriceFull файлы...")
try:
    scraper = ScraperFactory.SHUFERSAL.value()
    scraper.scrape(limit=2, files_types=[FileTypesFilters.PRICE_FULL_FILE.value])
    print("\nГотово! Скачалось:")
    count = check_results()
    if count == 0:
        print("  Файлы не найдены — попробуем без фильтра")
except AssertionError as e:
    print(f"Нет страниц для скачивания: {e}")
    print("Пробуем без фильтра по типу...")
    try:
        scraper = ScraperFactory.SHUFERSAL.value()
        scraper.scrape(limit=2)
        print("\nСкачалось:")
        check_results()
    except Exception as e2:
        print(f"Ошибка: {e2}")
except Exception as e:
    print(f"Ошибка: {e} ({type(e).__name__})")
