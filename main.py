import os
import subprocess
import sys
from parse_to_db import parse_and_insert

def run_pipeline():
    print("=== ЭТАП 1: Запуск скачивания файлов Supermarkets ===")
    scraper_script = "download_all.py"
    
    if os.path.exists(scraper_script):
        result = subprocess.run([sys.executable, scraper_script])
        if result.returncode != 0:
            print("Ошибка при выполнении скачивания файлов.")
            return
    else:
        print(f"Предупреждение: Файл {scraper_script} не найден. Пропускаем скачивание и парсим имеющиеся файлы.")

    print("\n=== ЭТАП 2: Парсинг XML и обновление базы данных ===")
    parse_and_insert()
    print("\n=== Пайплайн успешно завершен! ===")

if __name__ == "__main__":
    run_pipeline()