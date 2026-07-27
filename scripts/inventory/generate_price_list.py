#!/usr/bin/env python3
"""Generate an Excel price list and neutralize low-margin prices."""

from __future__ import annotations

import argparse
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.inventory.price_list import (
    BOOKS_PRICE_LIST_FIELDS,
    PriceListColumns,
    PriceListPolicy,
    generate_price_list,
    read_price_source,
    write_price_list,
)
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.config import Config


def resolve_purchase_account(account: str) -> tuple[str, str]:
    """Return the configured canonical account name and Zoho account ID."""

    requested = account.strip().casefold()
    for name, account_id in Config.PURCHASE_ACCOUNT_IDS.items():
        if requested in {str(name).strip().casefold(), str(account_id).strip().casefold()}:
            return str(name), str(account_id)
    configured = ", ".join(sorted(Config.PURCHASE_ACCOUNT_IDS)) or "none"
    raise ValueError(
        f"Purchase account {account!r} is not configured in PURCHASE_ACCOUNT_IDS. "
        f"Configured accounts: {configured}"
    )


def fetch_purchase_account_items(account_name: str, account_id: str) -> pd.DataFrame:
    """Fetch only the items assigned to one configured purchase account."""

    client = get_books_client()
    items = client.items.list_by_purchase_account(account_id)
    frame = pd.DataFrame(items)
    if frame.empty:
        raise ValueError(f"No items were returned for purchase account {account_name!r}")
    frame["purchase_account_name"] = account_name
    frame["purchase_account_id"] = account_id
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a price list and raise low-margin prices to the configured floor."
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Optional source .csv, .xlsx, or .xls file. Omit to fetch the account's items from Zoho Books.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Audit workbook to create. Defaults to "
            "output/inventory/price_lists/<purchase-account>/price_list.xlsx."
        ),
    )
    parser.add_argument(
        "--purchase-account",
        required=True,
        help="Exact purchase account name or ID to analyze. Only this account is processed.",
    )
    parser.add_argument("--sheet", default=0, help="Excel sheet name or zero-based sheet index.")
    parser.add_argument("--minimum-margin", type=Decimal, default=Decimal("15"))
    parser.add_argument("--expected-discount", type=Decimal, default=Decimal("0"))
    parser.add_argument("--rounding-increment", type=Decimal, default=Decimal("1"))
    parser.add_argument("--sku-column")
    parser.add_argument("--purchase-account-column")
    parser.add_argument("--name-column")
    parser.add_argument("--cost-column")
    parser.add_argument("--price-column")
    args = parser.parse_args()

    account_name, account_id = resolve_purchase_account(args.purchase_account)
    sheet: str | int = int(args.sheet) if str(args.sheet).isdigit() else args.sheet
    source = (
        read_price_source(args.source, sheet_name=sheet)
        if args.source
        else fetch_purchase_account_items(account_name, account_id)
    )
    policy = PriceListPolicy(
        minimum_margin_percent=args.minimum_margin,
        expected_discount_percent=args.expected_discount,
        rounding_increment=args.rounding_increment,
    )
    columns = PriceListColumns(
        purchase_account=args.purchase_account_column,
        sku=args.sku_column,
        name=args.name_column,
        cost=args.cost_column,
        price=args.price_column,
    )
    result = generate_price_list(
        source,
        purchase_account=account_name,
        policy=policy,
        columns=columns,
        source_output_columns=BOOKS_PRICE_LIST_FIELDS,
        inventory_tracked_only=True,
    )
    account_slug = re.sub(r"[^a-z0-9]+", "_", account_name.casefold()).strip("_")
    default_output = (
        Path("output/inventory/price_lists") / (account_slug or "purchase_account") / "price_list.xlsx"
    )
    destination = write_price_list(result, args.output or default_output)

    print(f"Created {destination} for purchase account: {account_name} ({account_id})")
    print(
        f"Rows: {result.summary['total_rows']} | "
        f"margin OK: {result.summary['margin_ok']} | "
        f"adjusted: {result.summary['adjusted_low_margin']} | "
        f"blocked: {result.summary['blocked']}"
    )
    if result.summary["blocked"]:
        print("Review the 'Blocked Rows' sheet before using the price list.")


if __name__ == "__main__":
    main()
