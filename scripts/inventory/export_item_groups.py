#!/usr/bin/env python3
"""Export all Zoho Inventory item groups to CSV."""

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import fetch_access_tokens, get_inventory_client
from zoho_usable_functions.core.logging_config import setup_logging


DEFAULT_OUTPUT = Path("output/inventory/item_groups.csv")


def item_group_to_row(group: dict[str, Any], default_status: str | None = None) -> dict[str, Any]:
    items = group.get("items")
    item_count = len(items) if isinstance(items, list) else group.get("items_count") or group.get("item_count")
    return {
        "item_group_id": group.get("item_group_id") or group.get("group_id") or group.get("id"),
        "name": group.get("name") or group.get("group_name"),
        "status": group.get("status") or default_status,
        "unit": group.get("unit"),
        "description": group.get("description"),
        "brand": group.get("brand"),
        "manufacturer": group.get("manufacturer"),
        "item_type": group.get("item_type"),
        "product_type": group.get("product_type"),
        "created_time": group.get("created_time"),
        "last_modified_time": group.get("last_modified_time"),
        "items_count": item_count,
        "variant_count": group.get("variant_count"),
        "category_id": group.get("category_id"),
        "category_name": group.get("category_name"),
        "account_id": group.get("account_id"),
        "purchase_account_id": group.get("purchase_account_id"),
        "inventory_account_id": group.get("inventory_account_id"),
    }


def export_item_groups(output_path: Path, active_only: bool = False) -> list[dict[str, Any]]:
    tokens = fetch_access_tokens()
    client = get_inventory_client(token=tokens.get("inventory"), allow_books_token=True)

    params = {"filter_by": "Status.Active"} if active_only else None
    groups = client.item_groups.list_all(params=params, resource_key="itemgroups")
    default_status = "active" if active_only else None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([item_group_to_row(group, default_status=default_status) for group in groups]).to_csv(output_path, index=False)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all Zoho Inventory item groups to CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV path to write.")
    parser.add_argument("--active-only", action="store_true", help="Export only active item groups.")
    args = parser.parse_args()

    setup_logging()

    filter_label = "active " if args.active_only else ""
    print(f"Fetching Zoho Inventory {filter_label}item groups...")
    groups = export_item_groups(args.output, active_only=args.active_only)
    print(f"Exported {len(groups)} item groups to {args.output}")


if __name__ == "__main__":
    main()
