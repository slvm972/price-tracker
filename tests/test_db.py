import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import database


def test_save_items_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.init_db()

    items = [
        {"barcode": "000123", "name": "Prod A", "price": 1.5, "brand": "B", "size": ""},
        {"barcode": "000124", "name": "Prod B", "price": 2.0, "brand": "B", "size": ""},
    ]
    saved = database.save_items_batch("TestRetail", "001", items, recorded_at="2026-01-01 00:00:00")
    assert saved >= 1

    stats = database.get_db_stats()
    assert stats["prices"] >= saved
    assert stats["stores"] >= 1


def test_dedup_same_price(tmp_path, monkeypatch):
    """Одинаковая цена не должна дважды записываться в БД."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.init_db()

    items = [{"barcode": "111", "name": "Item X", "price": 9.99, "brand": "", "size": ""}]
    saved1 = database.save_items_batch("R", "001", items, "2026-01-01 10:00:00")
    saved2 = database.save_items_batch("R", "001", items, "2026-01-01 11:00:00")
    assert saved1 == 1
    assert saved2 == 0  # цена не изменилась — дубль не пишется


def test_two_sequential_batches(tmp_path, monkeypatch):
    """Два батча для одного магазина не мешают друг другу (нет утечки кэша)."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.init_db()

    batch1 = [{"barcode": "AAA", "name": "X", "price": 5.0, "brand": "", "size": ""}]
    batch2 = [{"barcode": "BBB", "name": "Y", "price": 7.0, "brand": "", "size": ""}]
    s1 = database.save_items_batch("R", "001", batch1, "2026-01-01 10:00:00")
    s2 = database.save_items_batch("R", "001", batch2, "2026-01-01 11:00:00")
    assert s1 == 1
    assert s2 == 1

    stats = database.get_db_stats()
    assert stats["prices"] == 2


def test_save_promos_batch(tmp_path, monkeypatch):
    """Промо-акции записываются в таблицу promotions."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.init_db()

    # Сначала нужен товар в таблице products
    database.save_items_batch("R", "001",
        [{"barcode": "222", "name": "Promo Item", "price": 10.0, "brand": "", "size": ""}],
        "2026-01-01 10:00:00")

    promos = [{
        "barcode": "222", "name": "Promo Item",
        "promo_price": 7.5, "start_date": "2026-01-01", "end_date": "2026-01-07",
    }]
    saved = database.save_promos_batch("R", "001", promos, "2026-01-01 10:00:00")
    assert saved == 1

    stats = database.get_db_stats()
    assert stats["promotions"] == 1


def test_normalize_barcode():
    """Проверка корректной нормализации штрихкодов."""
    assert database.normalize_barcode("000123") == "123"
    assert database.normalize_barcode("  00123  ") == "123"
    assert database.normalize_barcode(123) == "123"
    assert database.normalize_barcode(None) == ""
    assert database.normalize_barcode("") == ""


def test_sqlite_version():
    """SQLite должна быть >= 3.25 для оконных функций."""
    import sqlite3
    assert sqlite3.sqlite_version_info >= (3, 25, 0), (
        f"SQLite {sqlite3.sqlite_version} слишком старый — нужен >= 3.25.0"
    )
