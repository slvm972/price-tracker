from il_supermarket_scarper import ScraperFactory
import inspect

# Смотрим исходный код Victory и других scrapers
chains = [
    ("VICTORY", ScraperFactory.VICTORY),
    ("SHUFERSAL", ScraperFactory.SHUFERSAL),
    ("YOHANANOF", ScraperFactory.YOHANANOF),
]

for name, factory in chains:
    print(f"\n{'='*50}")
    print(f"{name}")
    print("=" * 50)
    try:
        obj = factory.value()
        # Смотрим атрибуты объекта
        for attr in ["url", "base_url", "ftp_url", "price_url", "scraper_url"]:
            val = getattr(obj, attr, None)
            if val:
                print(f"  {attr}: {val}")

        # Смотрим исходный файл
        src_file = inspect.getfile(type(obj))
        print(f"  Файл: {src_file}")

        # Читаем исходник
        with open(src_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Ищем URL-ы в коде
        import re

        urls = re.findall(r'https?://[^\s\'"]+', content)
        urls += re.findall(r'ftp://[^\s\'"]+', content)
        for url in set(urls):
            if len(url) > 10:
                print(f"  URL: {url}")

    except Exception as e:
        print(f"  Ошибка: {e}")
