# -*- coding: utf-8 -*-
"""Дата из имени файла, сортировка, запрет отката и равных timestamp."""
import os
import sqlite3
from pathlib import Path

import database
from price_utils import (
    parse_filename_timestamp,
    recorded_at_from_price_file,
    sort_key_price_file,
)


def _init_db(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(database, "DB_PATH", str(db))
    database.init_db()
    return db


def test_parse_filename_timestamp_formats():
    assert parse_filename_timestamp(
        "Price7290803800003-000-013-20261004-144000.xml"
    ) == "2026-10-04 14:40:00"
    assert parse_filename_timestamp(
        "Price7290058173198-089-202610041402.xml"
    ) == "2026-10-04 14:02:00"
    assert parse_filename_timestamp(
        "PriceFull7290027600007-002-077-20261008-030000.xml"
    ) == "2026-10-08 03:00:00"
    assert parse_filename_timestamp(
        "x-20261004-115317.gz.xml.xml"
    ) == "2026-10-04 11:53:17"
    assert parse_filename_timestamp("nodate.xml") is None


def test_sort_reverse_alpha_by_publication(tmp_path):
    """Алфавит обратно датам: сортировка всё равно по возрастанию публикации."""
    names = [
        "Price729-000-Z-20261005-120000.xml",  # later alphabetically, later date
        "Price729-000-A-20261003-080000.xml",  # earlier alpha, earlier date
        "Price729-000-M-20261004-090000.xml",
    ]
    paths = []
    for n in names:
        path = tmp_path / n
        path.write_text("<Root/>", encoding="utf-8")
        paths.append(str(path))
    ordered = sorted(paths, key=sort_key_price_file)
    dates = [recorded_at_from_price_file(p) for p in ordered]
    assert dates == sorted(dates)
    assert "20261003" in os.path.basename(ordered[0])
    assert "20261005" in os.path.basename(ordered[-1])


def test_price_delta_newer_than_pricefull(tmp_path, monkeypatch):
    """Price (дельта) с более поздней датой в имени перекрывает PriceFull."""
    _init_db(tmp_path, monkeypatch)
    item = {
        "barcode": "7290222000001",
        "name": "Cheese",
        "price": 20.0,
        "brand": "B",
        "size": "",
        "weighted": False,
        "unit_price": 20.0,
    }
    # PriceFull older
    n1 = database.save_items_batch(
        "T", "001", [{**item, "price": 20.0}], recorded_at="2026-10-04 03:00:00"
    )
    assert n1 == 1
    # Delta newer, different price
    n2 = database.save_items_batch(
        "T", "001", [{**item, "price": 18.5}], recorded_at="2026-10-05 12:00:00"
    )
    assert n2 == 1
    conn = sqlite3.connect(database.DB_PATH)
    rows = conn.execute(
        "SELECT price, recorded_at FROM prices ORDER BY id"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[-1][0] == 18.5
    assert rows[-1][1] == "2026-10-05 12:00:00"


def test_reprocess_old_file_after_new(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    item = {
        "barcode": "7290222000002",
        "name": "Yogurt",
        "price": 7.0,
        "brand": "B",
        "size": "",
        "weighted": False,
        "unit_price": 7.0,
    }
    assert database.save_items_batch(
        "T", "001", [{**item, "price": 7.0}], recorded_at="2026-10-10 10:00:00"
    ) == 1
    # old file again with other price
    assert database.save_items_batch(
        "T", "001", [{**item, "price": 5.0}], recorded_at="2026-10-08 10:00:00"
    ) == 0
    conn = sqlite3.connect(database.DB_PATH)
    assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 1
    assert conn.execute("SELECT price FROM prices").fetchone()[0] == 7.0
    conn.close()


def test_equal_timestamp_different_price_no_insert(tmp_path, monkeypatch):
    """При одинаковом recorded_at другая цена не вставляется."""
    _init_db(tmp_path, monkeypatch)
    base = {
        "barcode": "7290222000003",
        "name": "Water",
        "brand": "B",
        "size": "",
        "weighted": False,
        "unit_price": 3.0,
    }
    assert database.save_items_batch(
        "T", "001", [{**base, "price": 3.0}], recorded_at="2026-10-04 14:40:00"
    ) == 1
    assert database.save_items_batch(
        "T", "001", [{**base, "price": 4.0}], recorded_at="2026-10-04 14:40:00"
    ) == 0
    conn = sqlite3.connect(database.DB_PATH)
    rows = conn.execute("SELECT price FROM prices").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 3.0


def test_backfill_meta_still_no_insert(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    item = {
        "barcode": "7290222000004",
        "name": "Salt",
        "price": 2.0,
        "brand": "B",
        "size": "",
        "weighted": None,
        "unit_price": None,
    }
    assert database.save_items_batch(
        "T", "001", [item], recorded_at="2026-10-10 10:00:00"
    ) == 1
    item2 = {**item, "weighted": False, "unit_price": 2.0, "price": 9.9}
    assert database.save_items_batch(
        "T", "001", [item2], recorded_at="2026-10-11 10:00:00", backfill_meta=True
    ) == 0
    conn = sqlite3.connect(database.DB_PATH)
    row = conn.execute(
        "SELECT price, is_weighted, unit_price FROM prices"
    ).fetchone()
    # backfill only updates when price matches — price 9.9 differs → no meta, no insert
    assert row[0] == 2.0
    assert row[1] is None
    # same price backfill
    item3 = {**item, "price": 2.0, "weighted": False, "unit_price": 2.0}
    assert database.save_items_batch(
        "T", "001", [item3], recorded_at="2026-10-11 10:00:00", backfill_meta=True
    ) == 0
    row = conn.execute(
        "SELECT price, is_weighted, unit_price FROM prices"
    ).fetchone()
    conn.close()
    assert row[0] == 2.0
    assert row[1] == 0
    assert abs(row[2] - 2.0) < 1e-9
