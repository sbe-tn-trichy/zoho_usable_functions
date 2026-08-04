#!/usr/bin/env python3
"""
Script to fetch the last invoiced prices for a customer using Zoho Analytics API.

Usage:
    uv run python scripts/books/get_customer_billed_prices.py --customer-id <CUSTOMER_ID> --sku SKU123 --qty 10 --sku SKU456 --qty 5
    uv run python scripts/books/get_customer_billed_prices.py --customer-id <CUSTOMER_ID> --items-json '[{"sku": "SKU123", "qty": 10}]'
"""

import argparse
import json
import logging
import sys
from typing import List, Dict, Any

from zoho_usable_functions import get_last_billed_prices_for_customer, init_script_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch last invoiced/billed prices for a customer using Zoho Analytics API."
    )
    parser.add_argument(
        "--customer-id",
        required=True,
        help="Zoho Books Customer ID or Customer Name",
    )
    parser.add_argument(
        "--workspace-id",
        help="Zoho Analytics Workspace ID (defaults to PAYMENT_ANALYTICS_WORKSPACE_ID in Config)",
    )
    parser.add_argument(
        "--sku",
        action="append",
        dest="skus",
        help="SKU code (can be specified multiple times)",
    )
    parser.add_argument(
        "--qty",
        action="append",
        dest="qtys",
        type=float,
        help="Requested quantity corresponding to each SKU (can be specified multiple times)",
    )
    parser.add_argument(
        "--items-json",
        help="JSON string of item dicts, e.g. '[{\"sku\": \"SKU1\", \"qty\": 10}]'",
    )
    parser.add_argument(
        "--view-name",
        help="Optional custom Analytics view name override",
    )
    parser.add_argument(
        "--output-json",
        help="Path to save output results JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    items: List[Dict[str, Any]] = []

    if args.items_json:
        try:
            items = json.loads(args.items_json)
        except Exception as e:
            logger.error("Failed to parse --items-json: %s", e)
            sys.exit(1)
    elif args.skus:
        skus = args.skus
        qtys = args.qtys or [1.0] * len(skus)
        if len(qtys) < len(skus):
            qtys.extend([1.0] * (len(skus) - len(qtys)))
        items = [{"sku": s, "qty": q} for s, q in zip(skus, qtys)]
    else:
        logger.error("Must provide either --sku / --qty flags or --items-json.")
        sys.exit(1)

    logger.info("Fetching last billed prices for customer: %s (%d items)", args.customer_id, len(items))

    init_script_context()

    try:
        result = get_last_billed_prices_for_customer(
            customer_id=args.customer_id,
            items=items,
            workspace_id=args.workspace_id,
            view_name=args.view_name,
        )
    except Exception as e:
        logger.error("Error fetching billed prices: %s", e)
        sys.exit(1)

    print("\n--- Last Billed Prices Summary ---")
    print(f"Customer ID : {result.customer_id}")
    print(f"Items Found : {result.found_count} / {result.item_count}\n")

    for item in result.items:
        if item.found:
            print(
                f"[FOUND] SKU: {item.sku} | Req Qty: {item.requested_qty} | "
                f"Last Rate: {item.last_billed_price} | Last Qty: {item.last_billed_qty} | "
                f"Inv #: {item.last_invoice_number} | Date: {item.last_invoice_date}"
            )
        else:
            print(f"[NOT FOUND] SKU: {item.sku} | Req Qty: {item.requested_qty} | No previous invoices found.")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        logger.info("Saved output to %s", args.output_json)


if __name__ == "__main__":
    main()
