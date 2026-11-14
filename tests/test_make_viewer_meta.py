import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import database
import make_viewer as mv


def _item(code, price):
    return {"barcode": code, "name": "Milk", "brand": "", "size": "",
            "price": price, "weighted": None, "unit_price": None}


def test_local_time_is_not_shifted():
    # раньше к времени из базы прибавлялось ещё 3 часа
    assert mv.to_israel_local("2026-11-14 16:14:51") == "2026-11-14 16:14:51"


def test_explicit_utc_is_converted():
    # в ноябре Израиль = UTC+2
    assert mv.to_israel_local("2026-11-14 10:00:00Z") == "2026-11-14 12:00:00"


def test_empty_or_bad_value_gives_a_valid_timestamp():
    for bad in (None, "", "не дата"):
        out = mv.to_israel_local(bad)
        assert len(out) == 19 and out[4] == "-" and out[10] == " "


def test_chain_updates_per_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "t.db"))
    database.init_db()
    database.save_items_batch("A", "001", [_item("7291111111111", 5.0)],
                              recorded_at="2026-11-14 09:00:00")
    database.save_items_batch("B", "001", [_item("7291111111111", 6.0)],
                              recorded_at="2026-10-11 09:00:00")
    assert mv.get_chain_updates() == {
        "A": "2026-11-14 09:00:00",
        "B": "2026-10-11 09:00:00",
    }


def test_render_data_js_has_three_constants():
    text = mv.render_data_js([{"c": "1"}], "2026-11-14 09:00:00", {"A": "2026-11-14 09:00:00"})
    assert text.startswith("const CATALOG = ")
    assert 'const CATALOG_UPDATED = "2026-11-14 09:00:00";' in text
    assert 'const CHAIN_UPDATED = {"A": "2026-11-14 09:00:00"};' in text
