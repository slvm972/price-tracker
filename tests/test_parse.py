import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from price_utils import parse_xml_to_items, parse_promo_xml

PADDING = "\n" + (" " * 600)


def test_parse_sample(tmp_path):
    xml = """<?xml version="1.0"?>
<Root>
  <StoreId>001</StoreId>
  <Items>
    <Item>
      <ItemCode>1234567890123</ItemCode>
      <ItemName>Test Product</ItemName>
      <ItemPrice>9.99</ItemPrice>
      <ManufacturerName>Acme</ManufacturerName>
      <UnitOfMeasure>kg</UnitOfMeasure>
      <Quantity>1</Quantity>
    </Item>
  </Items>
</Root>"""
    p = tmp_path / "Price001.xml"
    p.write_text(xml + PADDING, encoding="utf-8")

    store, items = parse_xml_to_items(str(p))
    assert store == "001"
    assert len(items) == 1
    it = items[0]
    assert it["barcode"] == "1234567890123"
    assert it["name"] == "Test Product"
    assert it["price"] == 9.99


def test_promo_file_skipped_by_price_parser(tmp_path):
    """Promo-файл должен игнорироваться парсером цен."""
    p = tmp_path / "Promo001.xml"
    p.write_text("<Root></Root>" + PADDING, encoding="utf-8")
    store, items = parse_xml_to_items(str(p))
    assert store is None
    assert items == []


def test_parse_promo_xml(tmp_path):
    xml = """<?xml version="1.0"?>
<Root>
  <StoreId>005</StoreId>
  <Sales>
    <Sale>
      <ItemCode>9876543210001</ItemCode>
      <ItemName>Sale Item</ItemName>
      <DiscountedPrice>4.50</DiscountedPrice>
      <StartDate>2026-06-01</StartDate>
      <EndDate>2026-06-07</EndDate>
    </Sale>
  </Sales>
</Root>"""
    p = tmp_path / "PromoFull005.xml"
    p.write_text(xml + PADDING, encoding="utf-8")

    store, promos = parse_promo_xml(str(p))
    assert store == "005"
    assert len(promos) == 1
    pr = promos[0]
    assert pr["barcode"] == "9876543210001"
    assert pr["promo_price"] == 4.50
    assert pr["start_date"] == "2026-06-01"
    assert pr["end_date"] == "2026-06-07"


def test_price_file_skipped_by_promo_parser(tmp_path):
    """Price-файл должен игнорироваться парсером промо."""
    p = tmp_path / "Price001.xml"
    p.write_text("<Root></Root>" + PADDING, encoding="utf-8")
    store, promos = parse_promo_xml(str(p))
    assert store is None
    assert promos == []
