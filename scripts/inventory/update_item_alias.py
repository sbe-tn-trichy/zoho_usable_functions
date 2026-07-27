#!/usr/bin/env python3
"""Sync Gemini invoice JSON names as alias_name on Zoho Books items."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.inventory.alias_sync import load_alias_mappings, sync_item_aliases


DEFAULT_MAPPING_FILE = Path("neoseal.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update json_name descriptions from mapping file as alias_name on Zoho Books items."
    )
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=DEFAULT_MAPPING_FILE,
        help="Path to mapping JSON file (default: neoseal.json).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually apply alias_name updates in Zoho Books. Defaults to dry-run.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite alias_name even if an alias already exists in Zoho Books.",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        help="Optional path to write full execution summary JSON.",
    )

    args = parser.parse_args()
    setup_logging()

    print(f"Loading mapping dataset from {args.mapping_file}...")
    mappings = load_alias_mappings(args.mapping_file)

    mode_label = "EXECUTE (MUTATING ZOHO)" if args.execute else "DRY-RUN (READ ONLY)"
    print(f"Running alias sync in {mode_label} mode (overwrite={args.overwrite})...")

    books_client = get_books_client()
    summary = sync_item_aliases(
        books_client=books_client,
        mappings=mappings,
        execute=args.execute,
        overwrite=args.overwrite,
    )

    print("\n=== ALIAS SYNC RESULTS SUMMARY ===")
    print(f"Total Mapped SKUs  : {summary['total_mapped_skus']}")
    print(f"Found in Zoho Books: {summary['found_in_zoho']}")
    print(f"Not Found in Zoho  : {summary['not_found_in_zoho']}")
    print(f"Items Updated      : {summary['updated']} ({'Applied' if args.execute else 'Dry Run'})")
    print(f"Items Skipped      : {summary['skipped']}")
    print(f"Errors             : {summary['errors']}")

    if summary["details"]:
        print("\n=== DETAIL LOG (First 10 items) ===")
        for detail in summary["details"][:10]:
            print(f"  [{detail['status'].upper()}] SKU: {detail['sku']} -> {detail.get('message') or detail.get('new_alias')}")

    if args.output_summary:
        args.output_summary.parent.mkdir(parents=True, exist_ok=True)
        with args.output_summary.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\nFull summary log written to {args.output_summary}")


if __name__ == "__main__":
    main()
