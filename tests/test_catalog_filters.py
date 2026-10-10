import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog_filters as cf


def row(barcode, retailer, price, name="Prod", size="", prev=None, brand=""):
    return {"barcode": barcode, "name": name, "brand": brand, "size": size,
            "retailer": retailer, "price": price, "previous_price": prev}


def test_placeholder_prices_are_dropped():
    assert not cf.is_valid_price(0.01)
    assert not cf.is_valid_price(0.1)
    assert cf.is_valid_price(0.5)
    assert cf.is_valid_price(9.9)


def test_short_or_non_numeric_barcodes_are_rejected():
    assert not cf.is_valid_barcode("11111")
    assert not cf.is_valid_barcode("1234567")
    assert cf.is_valid_barcode("7290117568859")
    assert not cf.is_valid_barcode("ABC1234567")


def test_internal_plu_codes_are_not_barcodes():
    # реальные примеры из XML: киви, шпинат, перец, хала, дрон — один код
    assert cf.is_internal_code("7290000000084")
    assert cf.is_internal_code("7290000006352")
    assert not cf.is_internal_code("7290000060958")  # настоящий штрихкод Assa
    assert not cf.is_valid_barcode("7290000000084")


def test_internal_codes_never_reach_catalog():
    rows = [row("7290000000084", "A", 19.9, name="kiwi"),
            row("7290000000084", "B", 9.9, name="pepper")]
    catalog, st = cf.build_catalog(rows, min_chains=1)
    assert catalog == [] and st["internal_code"] == 2


def test_non_product_words():
    assert cf.is_non_product("קופון ציפר")
    assert cf.is_non_product("מנויי תקופתי גוש דן")
    assert not cf.is_non_product("חלב תנובה 3%")


def test_clean_size():
    assert cf.clean_size("0.00 יחידות") == ""
    assert cf.clean_size("0.00 100 גרם") == "100 גרם"
    assert cf.clean_size("Unknown") == ""
    assert cf.clean_size("1.00 ליטר") == "1.00 ליטר"
    assert cf.clean_size(None) == ""


def test_outliers_three_chains():
    out = cf.drop_price_outliers({"A": 10.0, "B": 11.0, "C": 90.0})
    assert set(out) == {"A", "B"}


def test_two_chains_with_huge_gap_removes_item():
    assert cf.drop_price_outliers({"A": 1.0, "B": 149.0}) == {}
    assert cf.drop_price_outliers({"A": 10.0, "B": 12.0}) == {"A": 10.0, "B": 12.0}


def test_build_catalog_filters_and_aggregates():
    code = "7291111111111"
    rows = [
        row(code, "A", 10.0, size="0.00 יחידות"),
        row(code, "A", 9.0),                      # другой магазин той же сети: берём минимум
        row(code, "B", 11.0, prev=0.01),          # прошлая цена-заглушка не попадает в prev
        row("7291111111112", "A", 0.01),          # заглушка
        row("12345", "A", 5.0),                   # внутренний код
        row("7291111111113", "A", 5.0, name="קופון"),
        row("7291111111114", "A", 5.0),           # только одна сеть
    ]
    catalog, st = cf.build_catalog(rows, min_chains=2)
    assert [i["c"] for i in catalog] == [code]
    item = catalog[0]
    assert item["ch"] == {"A": 9.0, "B": 11.0}
    assert item["prev"] == {}
    assert item["s"] == ""
    assert st["bad_price"] == 1 and st["bad_barcode"] == 1 and st["non_product"] == 1
    assert st["items_dropped_min_chains"] == 1


def test_min_chains_one_keeps_single_chain_items():
    catalog, _ = cf.build_catalog([row("7291111111114", "A", 5.0)], min_chains=1)
    assert len(catalog) == 1


def test_catalog_is_sorted_by_name_then_barcode():
    rows = [
        row("7291111111112", "A", 5.0, name="b"), row("7291111111112", "B", 6.0, name="b"),
        row("7291111111111", "A", 5.0, name="a"), row("7291111111111", "B", 6.0, name="a"),
    ]
    catalog, _ = cf.build_catalog(rows)
    assert [i["n"] for i in catalog] == ["a", "b"]
