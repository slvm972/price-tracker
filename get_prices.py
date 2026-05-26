import requests

url = "https://prices.shufersal.co.il/FileObject/UpdateCategory?catID=0&storeId=0"
headers = {"User-Agent": "Mozilla/5.0"}

print("Подключаемся...")
try:
    r = requests.get(url, headers=headers, timeout=10)
    print("Статус:", r.status_code)
    print("Тип:", r.headers.get("Content-Type"))
    print(r.text[:500])
except Exception as e:
    print("Ошибка:", e)
