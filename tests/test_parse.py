import os
import sys
import pathlib

# ensure project root is on sys.path for imports
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from price_utils import parse_xml_to_items


def test_parse_sample(tmp_path):
    # create a minimal valid XML with one Item
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
</Root>
"""
    p = tmp_path / "sample.xml"
    # ensure file is large enough to pass size threshold in parser
    padding = "\n" + (" " * 600)
    p.write_text(xml + padding, encoding="utf-8")
    store, items = parse_xml_to_items(str(p))
    assert store == "001"
    assert isinstance(items, list)
    assert len(items) == 1
    it = items[0]
    assert it["barcode"] == "1234567890123"
    assert it["name"] == "Test Product"
    assert it["price"] == 9.99
