#!/usr/bin/env python3
"""Propose group assignments for active FAN items without an item group."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from zoho_usable_functions.core.cli import init_script_context
from zoho_usable_functions.inventory.fan_grouping import classify_item_type, propose_fan_group


def configure_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/inventory/proposed_group_assignments.csv"),
        help="Path to write group proposals CSV.",
    )


def main() -> None:
    ctx = init_script_context(
        description="Propose group assignments for active FAN items.",
        configure_parser=configure_args,
    )
    client = ctx.books_client
    args = ctx.args

    print("Fetching active items for FAN purchase account...")
    items = client.items.list_by_purchase_account("1094368000035990257", status="active")

    proposals: list[dict[str, Any]] = []
    for item in items:
        name = item.get("name") or item.get("item_name") or ""
        sku = item.get("sku") or ""
        current_group = item.get("group_name") or item.get("item_group_name") or ""

        if current_group:
            continue

        prod_type = classify_item_type(item)
        suggested_group, group_id, action = propose_fan_group(name, sku, prod_type)
        proposals.append(
            {
                "item_id": item.get("item_id"),
                "name": name,
                "sku": sku,
                "product_type": prod_type,
                "suggested_group": suggested_group,
                "group_id": group_id,
                "action": action,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if proposals:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(proposals[0].keys()))
            writer.writeheader()
            writer.writerows(proposals)

    print(f"Generated {len(proposals)} group proposals to {args.output}")


if __name__ == "__main__":
    main()
