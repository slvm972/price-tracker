import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tempfile
import database


def test_save_items_batch(tmp_path, monkeypatch):
    # point DB_PATH to a temporary file
    db_file = tmp_path / "test_prices.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))

    # initialize DB
    database.init_db()

    items = [
        {"barcode": "000123", "name": "Prod A", "price": 1.5, "brand": "B", "size": ""},
        {"barcode": "000124", "name": "Prod B", "price": 2.0, "brand": "B", "size": ""},
    ]

    saved = database.save_items_batch(
        "TestRetail", "001", items, recorded_at="2026-01-01 00:00:00"
    )
    assert saved >= 1

    stats = database.get_db_stats()
    assert stats["prices"] >= saved
    assert stats["stores"] >= 1
