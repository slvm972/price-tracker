# -*- coding: utf-8 -*-
"""Защита offline от отката цен к более старым дампам."""
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import database


def _init_tmp_db(tmp_path, monkeypatch, extra_cols=False):
    db = tmp_path / "t.db"
    monkeypatch.setattr(database, "DB_PATH", str(db))
    if extra_cols:
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY, barcode TEXT UNIQUE, name TEXT, brand TEXT, size TEXT
            );
            CREATE TABLE stores (
                id INTEGER PRIMARY KEY, retailer TEXT, store_code TEXT,
                UNIQUE(retailer, store_code)
            );
            CREATE TABLE prices (
                id INTEGER PRIMARY KEY, product_id INTEGER, store_id INTEGER,
                price REAL, recorded_at TEXT,
                chain_id TEXT, item_code TEXT, item_name TEXT
            );
            CREATE TABLE promotions (
                id INTEGER PRIMARY KEY, product_id INTEGER, store_id INTEGER,
                promo_price REAL, start_date TEXT, end_date TEXT
            );
            """
        )
        conn.close()
    database.init_db()
    return db


def test_older_file_price_not_inserted(tmp_path, monkeypatch):
    """Цена из более старого recorded_at не должна вставляться поверх новой."""
    _init_tmp_db(tmp_path, monkeypatch)

    items_new = [{
        "barcode": "7290111000001",
        "name": "Milk",
        "price": 10.0,
        "brand": "X",
        "size": "1L",
        "weighted": False,
        "unit_price": 10.0,
    }]
    n1 = database.save_items_batch(
        "TestChain", "001", items_new, recorded_at="2026-10-10 12:00:00"
    )
    assert n1 == 1

    items_old = [{
        "barcode": "7290111000001",
        "name": "Milk",
        "price": 8.0,  # старая/другая цена
        "brand": "X",
        "size": "1L",
        "weighted": False,
        "unit_price": 8.0,
    }]
    n2 = database.save_items_batch(
        "TestChain", "001", items_old, recorded_at="2026-10-09 12:00:00"
    )
    assert n2 == 0

    conn = sqlite3.connect(database.DB_PATH)
    rows = conn.execute(
        "SELECT price, recorded_at FROM prices ORDER BY id"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 10.0
    assert rows[0][1] == "2026-10-10 12:00:00"


def test_backfill_meta_no_insert(tmp_path, monkeypatch):
    _init_tmp_db(tmp_path, monkeypatch)

    items = [{
        "barcode": "7290111000002",
        "name": "Bread",
        "price": 5.0,
        "brand": "Y",
        "size": "",
        "weighted": None,
        "unit_price": None,
    }]
    assert database.save_items_batch(
        "TestChain", "001", items, recorded_at="2026-10-10 12:00:00"
    ) == 1

    items2 = [{
        "barcode": "7290111000002",
        "name": "Bread",
        "price": 5.0,
        "brand": "Y",
        "size": "",
        "weighted": True,
        "unit_price": 5.0,
    }]
    n = database.save_items_batch(
        "TestChain", "001", items2,
        recorded_at="2026-10-10 13:00:00",
        backfill_meta=True,
    )
    assert n == 0

    # другая цена + backfill — тоже без INSERT
    items3 = [{
        "barcode": "7290111000002",
        "name": "Bread",
        "price": 9.9,
        "brand": "Y",
        "size": "",
        "weighted": False,
        "unit_price": 9.9,
    }]
    n3 = database.save_items_batch(
        "TestChain", "001", items3,
        recorded_at="2026-10-11 10:00:00",
        backfill_meta=True,
    )
    assert n3 == 0

    conn = sqlite3.connect(database.DB_PATH)
    cnt = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    row = conn.execute(
        "SELECT is_weighted, unit_price, price FROM prices"
    ).fetchone()
    conn.close()
    assert cnt == 1
    assert row[0] == 1
    assert abs(row[1] - 5.0) < 1e-9
    assert row[2] == 5.0


def test_schema_with_extra_columns(tmp_path, monkeypatch):
    """INSERT не падает при legacy-колонках chain_id, item_code, item_name."""
    _init_tmp_db(tmp_path, monkeypatch, extra_cols=True)
    cols = {
        r[1]
        for r in sqlite3.connect(database.DB_PATH).execute("PRAGMA table_info(prices)")
    }
    assert "chain_id" in cols
    assert "is_weighted" in cols

    items = [{
        "barcode": "7290111000003",
        "name": "Eggs",
        "price": 12.0,
        "brand": "Z",
        "size": "12",
        "weighted": False,
        "unit_price": 1.0,
    }]
    n = database.save_items_batch(
        "TestChain", "002", items, recorded_at="2026-10-10 12:00:00"
    )
    assert n == 1

    conn = sqlite3.connect(database.DB_PATH)
    row = conn.execute(
        "SELECT price, is_weighted, unit_price FROM prices"
    ).fetchone()
    conn.close()
    assert row[0] == 12.0
    assert row[1] == 0
    assert abs(row[2] - 1.0) < 1e-9


