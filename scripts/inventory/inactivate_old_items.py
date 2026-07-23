#!/usr/bin/env python3
"""Find active Zoho Inventory items containing '_old' and mark them inactive."""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import fetch_access_tokens, get_inventory_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.inventory.item_sync import (
    find_active_items_with_name_containing,
    mark_inventory_items_inactive,
)


DEFAULT_OUTPUT = Path("output/inventory/active_old_items.csv")


def write_candidates_csv(items: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "item_id": item.get("item_id") or item.get("id"),
            "name": item.get("name"),
            "sku": item.get("sku"),
            "status": item.get("status"),
            "item_type": item.get("item_type"),
            "product_type": item.get("product_type"),
        }
        for item in items
    ]
    pd.DataFrame(rows).to_csv(output_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find active Zoho Inventory items whose names contain '_old' and optionally mark them inactive."
    )
    parser.add_argument("--needle", default="_old", help="Case-insensitive text to search in item names.")
    parser.add_argument("--execute", action="store_true", help="Mark the matched active items inactive.")
    parser.add_argument("--limit", type=int, default=None, help="Limit matched items for a test run.")
    parser.add_argument("--batch-size", type=int, default=200, help="Number of item IDs per inactive API call.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV path for matched active items.")
    args = parser.parse_args()

    setup_logging()

    tokens = fetch_access_tokens()
    client = get_inventory_client(token=tokens.get("inventory"), allow_books_token=True)

    print(f"Fetching active Zoho Inventory items with names containing {args.needle!r}...")
    items = find_active_items_with_name_containing(client, needle=args.needle)
    if args.limit is not None:
        items = items[: args.limit]

    write_candidates_csv(items, args.output)
    print(f"Matched active items: {len(items)}")
    print(f"Candidate CSV: {args.output}")

    if not items:
        return

    for item in items[:20]:
        item_id = item.get("item_id") or item.get("id")
        print(f"  {item_id} | {item.get('sku') or ''} | {item.get('name')}")
    if len(items) > 20:
        print(f"  ... and {len(items) - 20} more")

    if not args.execute:
        print("Dry-run complete. Re-run with --execute to mark these items inactive.")
        return

    item_ids = [item.get("item_id") or item.get("id") for item in items]
    results = mark_inventory_items_inactive(client, item_ids, batch_size=args.batch_size)

    success_count = sum(1 for result in results if result["code"] == 0)
    print(f"Inactive API calls succeeded: {success_count}/{len(results)}")
    for result in results:
        print(f"  {len(result['item_ids'])} item(s): code={result['code']} message={result['message']}")


if __name__ == "__main__":
    main()
