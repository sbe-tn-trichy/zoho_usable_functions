import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.inventory.fan_item_sync import (
    DEFAULT_CREATE_XLSX,
    DEFAULT_FAN_ACCOUNTS,
    DEFAULT_FAN_FILE,
    DEFAULT_OUTPUT_DIR,
    compare_fan_items_with_inventory,
    create_inventory_items_from_sheet,
    prepare_inventory_item_payloads,
)


def print_compare_summary(results):
    summary = results["summary"]
    paths = results["paths"]
    print(f"FAN candidate SKUs: {summary['fan_candidate_skus']}")
    print(f"Zoho Inventory item SKUs fetched: {summary['zoho_inventory_item_skus']}")
    print(f"Missing FAN SKUs: {summary['missing_fan_skus']}")
    print(f"Missing CSV: {paths['missing_csv']}")
    print(f"Missing XLSX: {paths['missing_xlsx']}")
    print(f"Existing snapshot: {paths['existing_snapshot']}")


def print_prepare_summary(results, create_xlsx):
    paths = results["paths"]
    print(f"Create source XLSX: {create_xlsx}")
    print(f"Items prepared from Missing_Items: {results['summary']['items_in_create_sheet']}")
    print(f"Payload preview JSON: {paths['preview_json']}")
    print(f"Payload preview CSV: {paths['preview_csv']}")
    print(f"Validation XLSX: {paths['validation_xlsx']}")
    if "results_csv" in paths:
        print(f"Create results CSV: {paths['results_csv']}")


def main():
    parser = argparse.ArgumentParser(description="Compare FAN stock SKUs with Zoho Inventory items.")
    parser.add_argument("--fan-file", type=Path, default=DEFAULT_FAN_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--account-id", default=DEFAULT_FAN_ACCOUNTS["account_id"])
    parser.add_argument("--purchase-account-id", default=DEFAULT_FAN_ACCOUNTS["purchase_account_id"])
    parser.add_argument("--inventory-account-id", default=DEFAULT_FAN_ACCOUNTS["inventory_account_id"])
    parser.add_argument("--existing-items-file", type=Path, default=None)
    parser.add_argument(
        "--prepare-create-items",
        type=Path,
        default=None,
        help="Read the edited Missing_Items sheet and write Zoho create payload/validation previews.",
    )
    parser.add_argument(
        "--execute-create-items",
        action="store_true",
        help="Create items in Zoho Inventory from --prepare-create-items after writing previews.",
    )
    args = parser.parse_args()

    setup_logging()

    if args.prepare_create_items or args.execute_create_items:
        create_xlsx = args.prepare_create_items or DEFAULT_CREATE_XLSX
        if args.execute_create_items:
            results = create_inventory_items_from_sheet(create_xlsx=create_xlsx, output_dir=args.output_dir)
        else:
            results = prepare_inventory_item_payloads(create_xlsx=create_xlsx, output_dir=args.output_dir)
        print_prepare_summary(results, create_xlsx)
        return

    accounts = {
        "account_id": args.account_id,
        "purchase_account_id": args.purchase_account_id,
        "inventory_account_id": args.inventory_account_id,
    }
    results = compare_fan_items_with_inventory(
        fan_file=args.fan_file,
        output_dir=args.output_dir,
        existing_items_file=args.existing_items_file,
        accounts=accounts,
        max_pages=args.max_pages,
    )
    print_compare_summary(results)


if __name__ == "__main__":
    main()
