#!/usr/bin/env python3
"""Correct and group the two Neoseal Damp Kill size variants."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"),
)

from zoho.base_client import BaseZohoClient
from zoho_usable_functions.core.auth import get_inventory_client


GROUP_NAME = "Damp Kill"
VARIANTS = (
    {
        "item_id": "1094368000051371153",
        "size": "10 L",
        "sku": "507-10-L",
        "name": "507 Damp Kill 10 L",
    },
    {
        "item_id": "1094368000051371193",
        "size": "20 L",
        "sku": "507-20-L",
        "name": "507 Damp Kill 20 L",
    },
)


def _common(details: list[dict[str, Any]], *fields: str) -> str:
    for field in fields:
        values = {
            str(detail.get(field) or "").strip()
            for detail in details
            if detail.get(field)
        }
        if len(values) == 1:
            return values.pop()
        if len(values) > 1:
            raise ValueError(f"Variants have inconsistent {field} values: {values}")
    return ""


def build_grouping_payload(details: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a validated Zoho grouping payload for the Damp Kill variants."""

    if len(details) != len(VARIANTS):
        raise ValueError(f"Expected {len(VARIANTS)} live item details")

    payload: dict[str, Any] = {
        "group_name": GROUP_NAME,
        "unit": _common(details, "unit") or "NOS",
        "purchase_account_id": _common(details, "purchase_account_id"),
        "account_id": _common(details, "account_id", "sales_account_id"),
        "inventory_account_id": _common(details, "inventory_account_id"),
        "attribute_name1": "Size",
        "items": [
            {
                "item_id": variant["item_id"],
                "sku": variant["sku"],
                "attribute_option_name1": variant["size"],
            }
            for variant in VARIANTS
        ],
    }
    category_id = _common(details, "category_id")
    if category_id:
        payload["category_id"] = category_id

    missing = [
        field
        for field in ("purchase_account_id", "account_id", "inventory_account_id")
        if not payload[field]
    ]
    if missing:
        raise ValueError("Live items are missing grouping fields: " + ", ".join(missing))
    return payload


def group_items(client: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Call Zoho Inventory's item-grouping endpoint."""

    return BaseZohoClient.request(
        client,
        method="POST",
        endpoint="items/grouping",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        data={"JSONString": json.dumps(payload)},
        params={"organization_id": client.organization_id},
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Correct and group Neoseal Damp Kill size variants."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the name, SKU, and grouping changes in Zoho Inventory.",
    )
    args = parser.parse_args()

    client = get_inventory_client(allow_books_token=True)
    details: list[dict[str, Any]] = []
    for variant in VARIANTS:
        response = client.items.get(variant["item_id"])
        detail = response.get("item", response)
        current_group = str(
            detail.get("group_name") or detail.get("item_group_name") or ""
        ).strip()
        current_name = str(detail.get("name") or "").strip()
        allowed_groups = {GROUP_NAME.casefold(), current_name.casefold()}
        if current_group and current_group.casefold() not in allowed_groups:
            raise ValueError(
                f"{variant['item_id']} already belongs to group {current_group!r}"
            )
        details.append(detail)
        print(
            f"{variant['size']}: {detail.get('name')} [{detail.get('sku')}] "
            f"-> {variant['name']} [{variant['sku']}] | "
            f"current group: {current_group or '<none>'} "
            f"({detail.get('group_id') or detail.get('item_group_id') or 'no ID'})"
        )

    payload = build_grouping_payload(details)
    print(json.dumps(payload, indent=2))
    if not args.execute:
        print("Dry run only. Use --execute to apply these changes.")
        return

    for variant, detail in zip(VARIANTS, details):
        changes = {}
        if str(detail.get("name") or "") != variant["name"]:
            changes["name"] = variant["name"]
        if str(detail.get("sku") or "") != variant["sku"]:
            changes["sku"] = variant["sku"]
        if changes:
            client.items.update(variant["item_id"], changes)
            print(f"Updated {variant['size']}: {', '.join(changes)}")

    response = group_items(client, payload)
    group = response.get("item_group", response)
    print(
        f"Created group {GROUP_NAME!r}: "
        f"{group.get('group_id') or group.get('item_group_id') or 'ID not returned'}"
    )


if __name__ == "__main__":
    main()
