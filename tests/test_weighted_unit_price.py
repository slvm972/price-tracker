# -*- coding: utf-8 -*-
"""Тесты парсинга weighted/unit_price и миграции/UPDATE prices."""
import os
import sqlite3
import tempfile
import textwrap
from pathlib import Path

import pytest

import database
import price_utils


def test_parse_weighted_helpers():
    assert price_utils._parse_weighted("1") is True
    assert price_utils._parse_weighted("0") is False
    assert price_utils._parse_weighted("") is None
    assert price_utils._parse_weighted(None) is None
    assert price_utils._parse_weighted("yes") is None


def test_parse_positive_float_helpers():
    assert price_utils._parse_positive_float("2.5") == 2.5
    assert price_utils._parse_positive_float("0") is None
    assert price_utils._parse_positive_float("0.00") is None
    assert price_utils._parse_positive_float("") is None
    assert price_utils._parse_positive_float("לא ידוע") is None
    assert price_utils._parse_positive_float("Unknown") is None
    assert price_utils._parse_positive_float("abc") is None


def test_parse_xml_weighted_fields(tmp_path):
    xml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <Root>
          <StoreID>001</StoreID>
          <Items>
            <Item>
              <ItemCode>7290001234567</ItemCode>
              <ItemName>עגבניות</ItemName>
              <ItemPrice>9.90</ItemPrice>
              <ManufactureName>Test</ManufactureName>
              <UnitOfMeasure>ק"ג</UnitOfMeasure>
              <Quantity>1.00</Quantity>
              <bIsWeighted>1</bIsWeighted>
              <UnitOfMeasurePrice>9.90</UnitOfMeasurePrice>
              <QtyInPackage>1</QtyInPackage>
            </Item>
            <Item>
              <ItemCode>7290001234568</ItemCode>
              <ItemName>חלב</ItemName>
              <ItemPrice>6.50</ItemPrice>
              <ManufactureName>Tnuva</ManufactureName>
              <UnitOfMeasure>ליטר</UnitOfMeasure>
              <Quantity>1</Quantity>
              <bIsWeighted>0</bIsWeighted>
              <UnitOfMeasurePrice>0.00</UnitOfMeasurePrice>
              <QtyInPackage>0</QtyInPackage>
            </Item>
            <Item>
              <ItemCode>7290001234569</ItemCode>
              <ItemName>לחם</ItemName>
              <ItemPrice>8.00</ItemPrice>
              <ManufactureName></ManufactureName>
              <UnitOfMeasure></UnitOfMeasure>
              <Quantity></Quantity>
              <bIsWeighted></bIsWeighted>
              <UnitOfMeasurePrice></UnitOfMeasurePrice>
              <QtyInPackage>לא ידוע</QtyInPackage>
            </Item>
          </Items>
        </Root>
    """)
    path = tmp_path / "Price729-001-test.xml"
    path.write_text(xml, encoding="utf-8")
    # size must be >= 500
    path.write_text(xml + (" <!--pad-->" * 40), encoding="utf-8")

    store, items = price_utils.parse_xml_to_items(str(path))
    assert store == "001"
    assert len(items) == 3

    by_code = {i["barcode"]: i for i in items}
    a = by_code["7290001234567"]
    assert a["weighted"] is True
    assert a["unit_price"] == 9.9
    assert a["qty_in_package"] == 1.0

    b = by_code["7290001234568"]
    assert b["weighted"] is False
    assert b["unit_price"] is None  # 0.00 -> None
    assert b["qty_in_package"] is None  # 0 -> None

    c = by_code["7290001234569"]
    assert c["weighted"] is None
    assert c["unit_price"] is None
    assert c["qty_in_package"] is None


def test_migration_adds_columns(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, barcode TEXT UNIQUE, name TEXT, brand TEXT, size TEXT
        );
        CREATE TABLE stores (
            id INTEGER PRIMARY KEY, retailer TEXT, store_code TEXT, UNIQUE(retailer, store_code)
        );
        CREATE TABLE prices (
            id INTEGER PRIMARY KEY, product_id INTEGER, store_id INTEGER, price REAL, recorded_at TEXT
        );
        CREATE TABLE promotions (
            id INTEGER PRIMARY KEY, product_id INTEGER, store_id INTEGER,
            promo_price REAL, start_date TEXT, end_date TEXT
        );
    """)
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", str(db))
    database.init_db()

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()}
    conn.close()
    assert "is_weighted" in cols
    assert "unit_price" in cols

    # second call is no-op
    database.init_db()
    conn = sqlite3.connect(str(db))
    cols2 = {r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()}
    conn.close()
    assert cols2 == cols


def test_update_last_row_when_price_unchanged(tmp_path, monkeypatch):
    db = tmp_path / "w.db"
    monkeypatch.setattr(database, "DB_PATH", str(db))
    database.init_db()

    items = [{
        "barcode": "7290999000001",
        "name": "Test Weighted",
        "price": 12.5,
        "brand": "B",
        "size": "1 kg",
        "weighted": None,
        "unit_price": None,
        "qty_in_package": None,
    }]
    n1 = database.save_items_batch("TestChain", "001", items, recorded_at="2026-10-10 12:00:00")
    assert n1 == 1

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM prices ORDER BY id DESC LIMIT 1").fetchone()
    assert row["price"] == 12.5
    assert row["is_weighted"] is None
    assert row["unit_price"] is None
    price_id = row["id"]
    count1 = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    conn.close()

    # same price, but now with metadata -> UPDATE last row
    items2 = [{
        "barcode": "7290999000001",
        "name": "Test Weighted",
        "price": 12.5,
        "brand": "B",
        "size": "1 kg",
        "weighted": True,
        "unit_price": 12.5,
        "qty_in_package": 1.0,
    }]
    n2 = database.save_items_batch("TestChain", "001", items2, recorded_at="2026-10-10 13:00:00")
    assert n2 == 0  # no new price row

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    count2 = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    row2 = conn.execute("SELECT * FROM prices WHERE id = ?", (price_id,)).fetchone()
    conn.close()
    assert count2 == count1
    assert row2["is_weighted"] == 1
    assert abs(row2["unit_price"] - 12.5) < 1e-9

    # price change -> new row
    items3 = [{
        "barcode": "7290999000001",
        "name": "Test Weighted",
        "price": 13.0,
        "brand": "B",
        "size": "1 kg",
        "weighted": True,
        "unit_price": 13.0,
        "qty_in_package": 1.0,
    }]
    n3 = database.save_items_batch("TestChain", "001", items3, recorded_at="2026-10-10 14:00:00")
    assert n3 == 1
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == count1 + 1
    conn.close()
