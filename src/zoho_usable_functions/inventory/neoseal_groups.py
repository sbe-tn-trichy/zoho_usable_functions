"""Consistent product-family grouping for Neoseal price-list items."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


NEOSEAL_GROUP_RULES: tuple[tuple[str, str], ...] = (
    (r"\bUPVC Ball Valve\b", "UPVC Ball Valve"),
    (r"\bPVC Ball Valve\b", "PVC Ball Valve"),
    (r"\bPVC-UPVC Solution\b", "PVC-UPVC Solvent"),
    (r"\bUPVC Solution\b", "UPVC Solvent"),
    (r"\bCPVC (?:Solution|Solvent Cement)\b", "CPVC Solvent"),
    (r"\bPVC Solution\b", "PVC Solvent"),
    (r"\bSBR Latex\b", "SBR Latex"),
    (r"\bCrack Filler\b", "Crack Filler"),
    (r"\bTerrace Coat\b", "Terrace Coat"),
    (r"\bDemp Kill\b|\bDamp Kill\b", "Damp Kill"),
    (r"\bNEOCEM\b", "Neocem"),
    (r"\bBitucoat\b", "Bitucoat"),
    (r"\bECO PRIME\b", "Eco Prime"),
    (r"\bSeal X\b", "Seal X"),
    (r"\bGP Silicone? Sealant\b", "GP Silicone Sealant"),
    (r"\bGasket Shellac\b", "Neoseal Others"),
    (r"\bNeoflex\b", "Neoseal Others"),
    (r"\bDrain Cleaner\b", "Neoseal Others"),
    (r"\bIWP 500\b", "IWP 500"),
    (r"\bND-40\b", "ND-40 Lubricant"),
    (r"\bPTFE Tape\b", "PTFE Tape"),
    (r"\bInsulation Tape\b", "Insulation Tape"),
    (r"\bSR 609\b", "SR 609"),
    (r"\bSaral Seal\b", "Saral Seal"),
    (r"\bQuick Leak Stop\b", "Quick Leak Stop"),
)


def neoseal_group_name(item_name: object) -> str | None:
    """Return the normalized product-family group for one Neoseal item."""

    name = str(item_name or "").strip()
    for pattern, group_name in NEOSEAL_GROUP_RULES:
        if re.search(pattern, name, flags=re.IGNORECASE):
            return group_name
    return None


def assign_neoseal_group_names(items: pd.DataFrame) -> pd.DataFrame:
    """Assign every item a Neoseal group and sort by group then item name."""

    grouped = items.copy()
    if "name" not in grouped.columns and "item_name" not in grouped.columns:
        raise ValueError("Neoseal grouping requires a name or item_name column")

    names = grouped.get("name", pd.Series(index=grouped.index, dtype=object))
    if "item_name" in grouped.columns:
        names = names.where(names.notna() & names.astype(str).str.strip().ne(""), grouped["item_name"])
    grouped["group_name"] = names.map(neoseal_group_name)

    unmatched = names[grouped["group_name"].isna()].astype(str).tolist()
    if unmatched:
        preview = ", ".join(unmatched[:10])
        raise ValueError(f"Neoseal group rules do not cover: {preview}")

    sort_columns = ["group_name"]
    if "name" in grouped.columns:
        sort_columns.append("name")
    return grouped.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def _common_field(details: list[dict[str, Any]], *fields: str) -> str:
    for field in fields:
        values = {str(detail.get(field) or "").strip() for detail in details if detail.get(field)}
        if len(values) == 1:
            return values.pop()
        if len(values) > 1:
            raise ValueError(f"Variants have inconsistent {field} values: {values}")
    return ""


def build_grouping_payload(
    group_name: str,
    variants: Sequence[dict[str, Any]],
    details: list[dict[str, Any]],
    attribute_name: str = "Size",
) -> dict[str, Any]:
    """Build a validated Zoho grouping payload for item variants."""

    if len(details) != len(variants):
        raise ValueError(f"Expected {len(variants)} live item details, got {len(details)}")

    payload: dict[str, Any] = {
        "group_name": group_name,
        "unit": _common_field(details, "unit") or "NOS",
        "purchase_account_id": _common_field(details, "purchase_account_id"),
        "account_id": _common_field(details, "account_id", "sales_account_id"),
        "inventory_account_id": _common_field(details, "inventory_account_id"),
        "attribute_name1": attribute_name,
        "items": [
            {
                "item_id": variant["item_id"],
                "sku": variant["sku"],
                "attribute_option_name1": variant.get("size") or variant.get("option", ""),
            }
            for variant in variants
        ],
    }
    category_id = _common_field(details, "category_id")
    if category_id:
        payload["category_id"] = category_id

    missing = [field for field in ("purchase_account_id", "account_id", "inventory_account_id") if not payload[field]]
    if missing:
        raise ValueError("Live items are missing grouping fields: " + ", ".join(missing))
    return payload


def post_item_grouping(client: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Group variants through the typed Zoho Inventory SDK resource."""
    return client.items.group_items(payload)
