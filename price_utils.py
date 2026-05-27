import os
import xml.etree.ElementTree as ET


def parse_xml_to_items(xml_path):
    """Читает один XML-файл, возвращает (store_code, [items])."""
    fname = os.path.basename(xml_path)
    if any(kw in fname for kw in ("Promo", "NULL", "promo", "null")):
        return None, []
    try:
        size = os.path.getsize(xml_path)
    except Exception:
        return None, []
    if size < 500:
        return None, []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        return None, []

    store_code = (
        root.findtext("StoreId")
        or root.findtext("BranchId")
        or root.findtext("SubChainID")
        or "000"
    )

    items = []
    for item in root.findall(".//Item"):
        barcode = (item.findtext("ItemCode") or "").strip()
        name = (item.findtext("ItemName") or "").strip()
        price = (item.findtext("ItemPrice") or "").strip()
        brand = (item.findtext("ManufacturerName") or "").strip()
        unit = (item.findtext("UnitOfMeasure") or "").strip()
        qty = (item.findtext("Quantity") or item.findtext("UnitQty") or "").strip()

        if not barcode or not name or not price:
            continue
        try:
            price_f = round(float(price), 2)
            if price_f <= 0:
                continue
        except ValueError:
            continue

        size_str = f"{qty} {unit}".strip() if (qty or unit) else ""
        items.append(
            {
                "barcode": barcode,
                "name": name,
                "price": price_f,
                "brand": brand,
                "size": size_str,
            }
        )

    return store_code, items
