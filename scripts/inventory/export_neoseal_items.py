#!/usr/bin/env python3
"""Download Neoseal purchase-account items and audit item name versus SKU."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from zoho_usable_functions.core.cli import init_script_context
from zoho_usable_functions.inventory.item_formatter import item_to_row_dict
from zoho_usable_functions.inventory.name_sku_audit import resolve_purchase_account

DEFAULT_OUTPUT = Path("output/inventory/neoseal_items_name_vs_sku.csv")


def configure_args(parser: argparse.ArgumentParser) -> None:
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
        default="active",
        help="Item status to download (default: active).",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV path to write.")


def main() -> None:
    ctx = init_script_context(
        description="Export all Neoseal purchase-account items with name-versus-SKU comparison columns.",
        configure_parser=configure_args,
    )
    client = ctx.books_client
    args = ctx.args

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
    rows = [item_to_row_dict(item) for item in items]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = list(item_to_row_dict({}).keys())
    pd.DataFrame(rows, columns=columns).to_csv(args.output, index=False)

    comparison_counts = pd.Series([row["comparison"] for row in rows]).value_counts()
    print(f"Exported {len(rows)} items to {args.output}")
    for comparison, count in comparison_counts.items():
        print(f"  {comparison}: {count}")


if __name__ == "__main__":
    main()
