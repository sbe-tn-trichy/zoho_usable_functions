#!/usr/bin/env python3
"""Create a review CSV for Neoseal item-group assignments; never updates Zoho."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_inventory_client
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.inventory.neoseal_groups import neoseal_group_name


DEFAULT_ACCOUNT_NAME = "Neoseal Purchase"
DEFAULT_OUTPUT = Path("output/inventory/neoseal_group_review.csv")


def _text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _is_inventory_tracked(item: dict[str, Any]) -> bool:
    value = item.get("track_inventory")
    return value is True or str(value).strip().casefold() in {"true", "1", "yes"}


def build_review_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build reviewable current-versus-proposed group rows."""

    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for item in items:
        if not _is_inventory_tracked(item):
            continue
        name = _text(item.get("name")) or _text(item.get("item_name"))
        proposed_group = neoseal_group_name(name)
        if not proposed_group:
            unmatched.append(name or str(item.get("item_id") or "<unnamed>"))
            continue
        current_group = _text(item.get("group_name"))
        rows.append(
            {
                "purchase_account_name": DEFAULT_ACCOUNT_NAME,
                "purchase_account_id": _text(item.get("purchase_account_id")),
                "item_id": _text(item.get("item_id")),
                "sku": _text(item.get("sku")),
                "name": name,
                "current_group_id": _text(
                    item.get("group_id") or item.get("item_group_id") or ""
                ),
                "current_group_name": current_group,
                "proposed_group_name": proposed_group,
                "change_required": current_group.casefold() != proposed_group.casefold(),
                "review_action": "PENDING",
                "review_notes": "",
            }
        )

    if unmatched:
        preview = ", ".join(unmatched[:10])
        raise ValueError(f"Group rules do not cover these tracked items: {preview}")
    return sorted(
        rows,
        key=lambda row: (row["proposed_group_name"].casefold(), row["name"].casefold()),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a review CSV for Neoseal item-group assignments. No Zoho writes."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional previously exported inventory-tracked CSV/XLSX snapshot; avoids a live Zoho fetch.",
    )
    args = parser.parse_args()

    account_id = str(Config.PURCHASE_ACCOUNT_IDS.get(DEFAULT_ACCOUNT_NAME) or "")
    if not account_id:
        raise ValueError(
            f"{DEFAULT_ACCOUNT_NAME!r} is missing from PURCHASE_ACCOUNT_IDS in .env"
        )

    if args.source:
        if args.source.suffix.lower() == ".csv":
            snapshot = pd.read_csv(args.source)
        elif args.source.suffix.lower() in {".xlsx", ".xls"}:
            snapshot = pd.read_excel(args.source, sheet_name="Price List")
        else:
            raise ValueError("--source must be a .csv, .xlsx, or .xls file")
        items = snapshot.to_dict("records")
        for item in items:
            item["track_inventory"] = True
            item["purchase_account_id"] = account_id
    else:
        client = get_inventory_client(allow_books_token=True)
        items = client.items.list_by_purchase_account(account_id)
    rows = build_review_rows(items)
    if not rows:
        raise ValueError("No inventory-tracked Neoseal items were returned")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    changes = sum(bool(row["change_required"]) for row in rows)
    groups = len({row["proposed_group_name"] for row in rows})
    print(f"Created review CSV: {args.output}")
    print(f"Tracked items: {len(rows)} | proposed groups: {groups} | changes: {changes}")
    print("No Zoho records were changed. Set review_action to APPROVE or SKIP after review.")


if __name__ == "__main__":
    main()
