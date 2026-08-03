#!/usr/bin/env python3
"""Correct and group the two Neoseal Damp Kill size variants."""

from __future__ import annotations

import argparse
import json
from typing import Any

from zoho_usable_functions.core.cli import init_script_context
from zoho_usable_functions.inventory.neoseal_groups import (
    build_grouping_payload as core_build_grouping_payload,
    post_item_grouping,
)

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


def build_grouping_payload(details: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a validated Zoho grouping payload for the Damp Kill variants."""
    return core_build_grouping_payload(GROUP_NAME, VARIANTS, details)


def configure_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the name, SKU, and grouping changes in Zoho Inventory.",
    )


def main() -> None:
    ctx = init_script_context(
        description="Correct and group Neoseal Damp Kill size variants.",
        configure_parser=configure_args,
    )
    client = ctx.books_client
    args = ctx.args

    details: list[dict[str, Any]] = []
    for variant in VARIANTS:
        response = client.items.get(variant["item_id"])
        detail = response.get("item", response)
        current_group = str(detail.get("group_name") or detail.get("item_group_name") or "").strip()
        current_name = str(detail.get("name") or "").strip()
        allowed_groups = {GROUP_NAME.casefold(), current_name.casefold()}
        if current_group and current_group.casefold() not in allowed_groups:
            raise ValueError(f"{variant['item_id']} already belongs to group {current_group!r}")
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

    response = post_item_grouping(client, payload)
    group = response.get("item_group", response)
    print(
        f"Created group {GROUP_NAME!r}: "
        f"{group.get('group_id') or group.get('item_group_id') or 'ID not returned'}"
    )


if __name__ == "__main__":
    main()
