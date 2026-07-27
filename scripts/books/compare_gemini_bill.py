#!/usr/bin/env python3
"""Retrieve a Zoho bill and compare it with Gemini invoice JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from zoho_usable_functions.books.bill_json_audit import (
    build_name_sku_mapping,
    compare_invoice_json_to_bill,
    find_bill_by_number,
    merge_name_sku_mappings,
    normalize_invoice_json,
)
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging


DEFAULT_OUTPUT = Path("output/books/gemini_bill_comparison.json")
DEFAULT_MAPPING_OUTPUT = Path("neoseal.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Gemini invoice JSON with its Zoho Books bill.")
    parser.add_argument("json_file", type=Path, help="Gemini JSON file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Audit JSON path.")
    parser.add_argument(
        "--mapping-output",
        type=Path,
        default=DEFAULT_MAPPING_OUTPUT,
        help="Persistent JSON mapping dataset; existing invoice mappings are updated.",
    )
    parser.add_argument("--amount-tolerance", type=float, default=0.05)
    parser.add_argument("--minimum-name-similarity", type=float, default=0.60)
    args = parser.parse_args()

    setup_logging()
    with args.json_file.open(encoding="utf-8") as file_handle:
        invoice_json = json.load(file_handle)

    bill_number = normalize_invoice_json(invoice_json).get("inv", {}).get("no")
    if not bill_number:
        raise ValueError("Gemini JSON is missing inv.no")

    client = get_books_client()
    print(f"Looking for Zoho Books bill {bill_number}...")
    bill = find_bill_by_number(client, bill_number)
    if bill is None:
        report = {"bill_found": False, "bill_number": bill_number}
        print("Bill not found.")
    else:
        report = compare_invoice_json_to_bill(
            invoice_json,
            bill,
            amount_tolerance=args.amount_tolerance,
            minimum_similarity=args.minimum_name_similarity,
        )
        summary = report["summary"]
        print(f"Bill found: {report['bill_id']}")
        print(f"Matched lines: {summary['matched_lines']}/{summary['json_lines']}")
        print(f"Lines with differences: {summary['lines_with_differences']}")
        print(f"Overall match: {summary['overall_match']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file_handle:
        json.dump(report, file_handle, indent=2, ensure_ascii=False)
    print(f"Comparison report: {args.output}")

    mapping = build_name_sku_mapping(report)
    existing_mapping = []
    if args.mapping_output.exists():
        with args.mapping_output.open(encoding="utf-8") as file_handle:
            existing_mapping = json.load(file_handle)
        if not isinstance(existing_mapping, list):
            raise ValueError(f"{args.mapping_output} must contain a JSON array")
    mapping = merge_name_sku_mappings(existing_mapping, mapping)
    args.mapping_output.parent.mkdir(parents=True, exist_ok=True)
    with args.mapping_output.open("w", encoding="utf-8") as file_handle:
        json.dump(mapping, file_handle, indent=2, ensure_ascii=False)
    print(f"Name/SKU mapping: {args.mapping_output}")


if __name__ == "__main__":
    main()
