import os
import xml.etree.ElementTree as ET


def _find_text(el, *tags):
    """Ищет первый из перечисленных тегов в элементе."""
    for tag in tags:
        val = el.findtext(tag)
        if val is not None:
            return val.strip()
    return ""


def parse_xml_to_items(xml_path):
    """
    Читает один Price*.xml-файл, возвращает (store_code, [items]).
    Promo-файлы и NULL-файлы пропускаются (возвращают None, []).
    """
    fname = os.path.basename(xml_path)
    if any(kw in fname for kw in ("Promo", "promo", "NULL", "null")):
        return None, []
    try:
        size = os.path.getsize(xml_path)
    except Exception:
        return None, []
    if size < 500:
        return None, []
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return None, []

    store_code = (
        root.findtext("StoreId")
        or root.findtext("BranchId")
        or root.findtext("SubChainID")
        or "000"
    )

    items = []
    for item in root.findall(".//Item"):
        barcode = _find_text(item, "ItemCode")
        name    = _find_text(item, "ItemName", "ItemNm", "ManufacturerItemDescription")
        price   = _find_text(item, "ItemPrice")
        brand   = _find_text(item, "ManufacturerName")
        unit    = _find_text(item, "UnitOfMeasure")
        qty     = _find_text(item, "Quantity", "UnitQty")

        if not barcode or not name or not price:
            continue
        try:
            price_f = round(float(price), 2)
            if price_f <= 0:
                continue
        except ValueError:
            continue

        size_str = f"{qty} {unit}".strip() if (qty or unit) else ""
        items.append({
            "barcode": barcode,
            "name":    name,
            "price":   price_f,
            "brand":   brand,
            "size":    size_str,
        })

    return store_code, items


def parse_promo_xml(xml_path):
    """
    Читает один Promo*.xml-файл, возвращает (store_code, [promos]).
    Каждый промо-объект: {barcode, name, promo_price, start_date, end_date}.
    Price-файлы пропускаются (возвращают None, []).
    """
    fname = os.path.basename(xml_path)
    if not any(kw in fname for kw in ("Promo", "promo")):
        return None, []
    if any(kw in fname for kw in ("NULL", "null")):
        return None, []
    try:
        size = os.path.getsize(xml_path)
    except Exception:
        return None, []
    if size < 200:
        return None, []
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return None, []

    store_code = (
        root.findtext("StoreId")
        or root.findtext("BranchId")
        or root.findtext("SubChainID")
        or "000"
    )

    promos = []
    # Акции могут лежать в <Sale>, <Promotion>, <Promo> или <Item> в зависимости от сети
    for sale in root.findall(".//*[DiscountedPrice]") or root.findall(".//*[SalePrice]") or []:
        barcode     = _find_text(sale, "ItemCode", "MemberItemCode")
        name        = _find_text(sale, "ItemName")
        promo_price = _find_text(sale, "DiscountedPrice", "SalePrice", "PromoPrice")
        start_date  = _find_text(sale, "StartDate", "PromotionStartDate")
        end_date    = _find_text(sale, "EndDate", "PromotionEndDate")

        if not barcode or not promo_price:
            continue
        try:
            pp = round(float(promo_price), 2)
            if pp <= 0:
                continue
        except ValueError:
            continue

        promos.append({
            "barcode":     barcode,
            "name":        name,
            "promo_price": pp,
            "start_date":  start_date or None,
            "end_date":    end_date or None,
        })

    return store_code, promos
