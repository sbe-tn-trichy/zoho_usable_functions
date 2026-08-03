"""Utilities for formatting and extracting attributes from Zoho Inventory item dictionaries."""

from __future__ import annotations

from typing import Any

from .name_sku_audit import compare_name_to_sku


def extract_group_attributes(item: dict[str, Any]) -> str:
    """Format group attribute key/value pairs from item dict into a semicolon-separated string."""
    attrs: list[str] = []
    for k in (1, 2, 3):
        an = item.get(f"attribute_name{k}")
        aon = item.get(f"attribute_option_name{k}")
        if an or aon:
            val = str(aon or "").strip()
            key = str(an or "").strip()
            if key and val:
                attrs.append(f"{key}={val}")
            elif val:
                attrs.append(val)
            elif key:
                attrs.append(key)
    return "; ".join(attrs)


def item_to_row_dict(item: dict[str, Any], include_audit: bool = True) -> dict[str, Any]:
    """Flatten a Zoho Inventory item dictionary into a normalized row dictionary for reporting/exporting."""
    name = item.get("name") or item.get("item_name") or ""
    sku = item.get("sku") or item.get("item_sku") or ""
    group_name = item.get("group_name") or item.get("item_group_name") or ""

    row: dict[str, Any] = {
        "item_id": item.get("item_id") or item.get("id") or "",
        "name": name,
        "sku": sku,
        "group_id": item.get("group_id") or item.get("item_group_id") or "",
        "group_name": group_name,
        "group_attributes": extract_group_attributes(item),
        "attribute_name1": item.get("attribute_name1") or "",
        "attribute_option_name1": item.get("attribute_option_name1") or "",
        "attribute_name2": item.get("attribute_name2") or "",
        "attribute_option_name2": item.get("attribute_option_name2") or "",
        "attribute_name3": item.get("attribute_name3") or "",
        "attribute_option_name3": item.get("attribute_option_name3") or "",
    }

    if include_audit:
        row.update(compare_name_to_sku(name, sku))

    row.update(
        {
            "status": item.get("status"),
            "unit": item.get("unit"),
            "rate": item.get("rate"),
            "purchase_rate": item.get("purchase_rate"),
            "stock_on_hand": item.get("stock_on_hand"),
            "purchase_account_id": item.get("purchase_account_id"),
            "purchase_account_name": item.get("purchase_account_name"),
            "item_type": item.get("item_type"),
            "product_type": item.get("product_type"),
            "manufacturer": item.get("manufacturer"),
            "brand": item.get("brand"),
            "hsn_or_sac": item.get("hsn_or_sac"),
        }
    )

    return row
