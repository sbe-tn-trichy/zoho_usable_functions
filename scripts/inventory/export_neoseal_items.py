#!/usr/bin/env python3
"""Download Neoseal purchase-account items and audit item name versus SKU."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import fetch_access_tokens, get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.inventory.name_sku_audit import compare_name_to_sku, resolve_purchase_account


DEFAULT_OUTPUT = Path("output/inventory/neoseal_items_name_vs_sku.csv")


def item_to_row(item: dict[str, Any]) -> dict[str, Any]:
    name = item.get("name") or item.get("item_name") or ""
    sku = item.get("sku") or item.get("item_sku") or ""
    return {
        "item_id": item.get("item_id") or item.get("id"),
        "name": name,
        "sku": sku,
        **compare_name_to_sku(name, sku),
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export all Neoseal purchase-account items with name-versus-SKU comparison columns."
    )
    parser.add_argument(
        "--account-name",
        default="Neoseal",
        help="Exact or unique partial purchase-account name (default: Neoseal).",
    )
    parser.add_argument(
        "--purchase-account-id",
        help="Use this purchase-account ID instead of resolving --account-name.",
    )
    parser.add_argument(
        "--status",
        choices=("all", "active", "inactive"),
        default="all",
        help="Item status to download (default: all).",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV path to write.")
    args = parser.parse_args()

    setup_logging()
    tokens = fetch_access_tokens()
    client = get_books_client(token=tokens.get("books"))

    account_id = args.purchase_account_id
    account_name = args.account_name
    if not account_id:
        accounts = client.chart_of_accounts.list_all()
        account = resolve_purchase_account(accounts, args.account_name)
        account_id = account.get("account_id") or account.get("id")
        account_name = account.get("account_name") or account.get("name")
        if not account_id:
            raise ValueError(f"Matched purchase account {account_name!r} has no account ID")

    print(f"Fetching {args.status} items for {account_name} ({account_id})...")
    items = client.items.list_by_purchase_account(account_id, status=args.status)
    rows = [item_to_row(item) for item in items]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = list(item_to_row({}).keys())
    pd.DataFrame(rows, columns=columns).to_csv(args.output, index=False)

    comparison_counts = pd.Series([row["comparison"] for row in rows]).value_counts()
    print(f"Exported {len(rows)} items to {args.output}")
    for comparison, count in comparison_counts.items():
        print(f"  {comparison}: {count}")


if __name__ == "__main__":
    main()
