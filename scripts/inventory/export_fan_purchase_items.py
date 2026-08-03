#!/usr/bin/env python3
"""Export and categorize fan purchase items to CSV."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
from typing import Any

from zoho_usable_functions.core.cli import init_script_context
from zoho_usable_functions.inventory.fan_grouping import classify_item_type

logger = logging.getLogger(__name__)


def configure_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/inventory/fan_purchase_items.csv"),
        help="Path to save exported fan items CSV.",
    )


def main() -> None:
    ctx = init_script_context(
        description="Export and categorize FAN purchase items to CSV.",
        configure_parser=configure_args,
    )
    client = ctx.books_client
    args = ctx.args

    print("Fetching items for FAN purchase account...")
    items = client.items.list_by_purchase_account("1094368000035990257", status="all")

    rows: list[dict[str, Any]] = []
    for item in items:
        prod_type = classify_item_type(item)
        rows.append(
            {
                "item_id": item.get("item_id"),
                "name": item.get("name") or item.get("item_name"),
                "sku": item.get("sku"),
                "product_type": prod_type,
                "status": item.get("status"),
                "rate": item.get("rate"),
                "purchase_rate": item.get("purchase_rate"),
                "group_name": item.get("group_name") or item.get("item_group_name"),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"Exported {len(rows)} fan items to {args.output}")


if __name__ == "__main__":
    main()
