#!/usr/bin/env python3
"""
Script to renumber July 2026 split invoices sequentially from SBE2627INV-00451 
to SBE2627INV-00465 in date order, eliminating all sequence gaps.
"""

import sys
import json
import argparse
from pathlib import Path

# Add repo src and sibling zoho_sdk/src to sys.path if not installed
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT.parent / "zoho_sdk" / "src"
SRC_ROOT = REPO_ROOT / "src"

if str(SDK_ROOT) not in sys.path and SDK_ROOT.exists():
    sys.path.insert(0, str(SDK_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zoho_usable_functions.core.auth import get_books_client

# Target renumbering mapping ordered chronologically by date
RENUMBER_MAPPING = [
    ("1094368000058794006", "SBE2627INV-00451", "2026-07-18"),
    ("1094368000058806016", "SBE2627INV-00452", "2026-07-18"),
    ("1094368000058798029", "SBE2627INV-00453", "2026-07-20"),
    ("1094368000058798051", "SBE2627INV-00454", "2026-07-21"),
    ("1094368000058812034", "SBE2627INV-00455", "2026-07-22"),
    ("1094368000058792041", "SBE2627INV-00456", "2026-07-23"),
    ("1094368000058810026", "SBE2627INV-00457", "2026-07-24"),
    ("1094368000058805080", "SBE2627INV-00458", "2026-07-25"),
    ("1094368000058800003", "SBE2627INV-00459", "2026-07-27"),
    ("1094368000058789023", "SBE2627INV-00460", "2026-07-28"),
    ("1094368000058788626", "SBE2627INV-00461", "2026-07-29"),
    ("1094368000058807026", "SBE2627INV-00462", "2026-07-30"),
    ("1094368000058799005", "SBE2627INV-00463", "2026-07-31"),
    ("1094368000058801013", "SBE2627INV-00464", "2026-07-31"),
    ("1094368000058806039", "SBE2627INV-00465", "2026-07-31"),
]


def main():
    parser = argparse.ArgumentParser(description="Renumber July 2026 invoices sequentially.")
    parser.add_argument("--execute", action="store_true", help="Execute renumbering changes in Zoho Books.")
    args = parser.parse_args()

    client = get_books_client()

    print(f"Preparing to renumber {len(RENUMBER_MAPPING)} invoices in date order:")
    print("=" * 90)
    print(f"{'#':<3} | {'Invoice ID':<22} | {'Date':<10} | {'Target Invoice Number':<20}")
    print("=" * 90)

    for idx, (inv_id, new_no, inv_date) in enumerate(RENUMBER_MAPPING, 1):
        print(f"{idx:<3} | {inv_id:<22} | {inv_date:<10} | {new_no:<20}")
    
    print("=" * 90)

    if not args.execute:
        print("\n[DRY RUN COMPLETE] Pass '--execute' to perform renumbering in Zoho Books.")
        return

    print("\n--- EXECUTING INVOICE RENUMBERING IN ZOHO BOOKS ---")
    updated_count = 0

    for idx, (inv_id, new_no, inv_date) in enumerate(RENUMBER_MAPPING, 1):
        print(f"[{idx}/{len(RENUMBER_MAPPING)}] Updating Invoice ID {inv_id} to number '{new_no}' (Date: {inv_date})...")
        try:
            res = client.invoices.get(inv_id)
            inv = res["invoice"]
            
            payload = {
                "customer_id": inv["customer_id"],
                "invoice_number": new_no,
                "date": inv_date,
                "line_items": inv["line_items"],
            }
            
            update_res = client.invoices.update(
                inv_id, payload, params={"ignore_auto_number_generation": "true"}
            )
            updated_inv = update_res.get("invoice", {})
            print(f"  -> Successfully updated to: {updated_inv.get('invoice_number')}")
            updated_count += 1
        except Exception as e:
            print(f"  -> Error updating invoice {inv_id}: {e}")
            sys.exit(1)

    print(f"\nAll {updated_count} invoices successfully renumbered!")
    print("=== RENUMBERING COMPLETE ===")


if __name__ == "__main__":
    main()
