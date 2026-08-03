#!/usr/bin/env python3
"""
Script to create and update contra Purchase Bills in location SBE to 100% match 
Sales Invoices SBE2627INV-00451 through SBE2627INV-00466 on Bill Number, Date, and Amount (including Round Off adjustment).
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

from zoho import HttpTokenProvider
from zoho_usable_functions.core.auth import get_books_client

VENDOR_ID = "1094368000048236978"  # Sri Bharath Electricals
BRANCH_ID = "1094368000044509446"  # SBE Location
DEFAULT_ACCOUNT_ID = "1094368000035130337" # Polycab Fan Stock
TAX_ID = "1094368000000014273"     # GST18

TARGET_INVOICES = [f"SBE2627INV-{i:05d}" for i in range(451, 467)]


def main():
    parser = argparse.ArgumentParser(description="Sync contra purchase bills in location SBE with round off.")
    parser.add_argument("--execute", action="store_true", help="Execute changes in Zoho Books.")
    args = parser.parse_args()

    tokens = HttpTokenProvider('http://localhost:3000/server/new/tokens').get_tokens()
    client = get_books_client(token=tokens['books'])

    print("Checking Sales Invoices and Contra Bills for SBE2627INV-00451 through 00466...")
    actions = []

    for inv_no in TARGET_INVOICES:
        # Fetch Sales Invoice
        inv_res = client.invoices.list(params={'invoice_number': inv_no})
        invs = inv_res.get('invoices', [])
        if not invs:
            print(f"Sales Invoice {inv_no} not found! Skipping.")
            continue
        
        full_inv = client.invoices.get(invs[0]['invoice_id'])['invoice']
        inv_date = full_inv.get('date')
        inv_tot = float(full_inv.get('total', 0.0))
        
        # Check existing bill
        bill_res = client.bills.list(params={'bill_number': inv_no})
        bills = bill_res.get('bills', [])
        
        action_type = "UPDATE" if bills else "CREATE NEW"
        bill_id = bills[0]['bill_id'] if bills else None
        
        actions.append({
            'sales_invoice': full_inv,
            'action_type': action_type,
            'existing_bill_id': bill_id,
            'target_number': inv_no,
            'target_date': inv_date,
            'target_total': inv_tot
        })

    print("\nSynchronization Action Plan (with Round Off Adjustment):")
    print("=" * 110)
    print(f"{'#':<3} | {'Sales Inv Number':<18} | {'Date':<10} | {'Sales Total (Rs.)':<16} | {'Action':<15} | {'Bill ID'}")
    print("=" * 110)

    for idx, item in enumerate(actions, 1):
        b_id_str = item['existing_bill_id'] or "NEW"
        print(f"{idx:<3} | {item['target_number']:<18} | {item['target_date']:<10} | {item['target_total']:>16,.2f} | {item['action_type']:<15} | {b_id_str}")

    print("=" * 110)

    if not args.execute:
        print("\n[DRY RUN COMPLETE] Pass '--execute' to create/update purchase bills with round off in Zoho Books.")
        return

    print("\n--- EXECUTING CONTRA BILL SYNCHRONIZATION WITH ROUND OFF IN ZOHO BOOKS ---")
    synced_count = 0

    for idx, item in enumerate(actions, 1):
        inv = item['sales_invoice']
        inv_no = item['target_number']
        inv_date = item['target_date']
        action = item['action_type']
        bill_id = item['existing_bill_id']
        target_total = item['target_total']
        
        print(f"[{idx}/{len(actions)}] {action} Bill for '{inv_no}' (Date: {inv_date}, Target Total: Rs. {target_total:,.2f})...")
        
        bill_line_items = []
        subtotal_calc = 0.0
        tax_calc = 0.0

        for l in inv.get('line_items', []):
            item_id = l.get('item_id')
            rate = float(l.get('rate') or l.get('bcy_rate') or 0.0)
            qty = float(l.get('quantity') or 0.0)
            
            item_sub = rate * qty
            item_tax = round(item_sub * 0.18, 2)
            subtotal_calc += item_sub
            tax_calc += item_tax
            
            # Fetch item's inventory/purchase account
            acc_id = DEFAULT_ACCOUNT_ID
            try:
                item_detail = client.items.get(item_id)['item']
                acc_id = item_detail.get('inventory_account_id') or item_detail.get('purchase_account_id') or DEFAULT_ACCOUNT_ID
            except Exception:
                pass
            
            b_item = {
                "item_id": item_id,
                "name": l.get('name'),
                "account_id": acc_id,
                "rate": rate,
                "quantity": qty,
                "tax_id": TAX_ID,
                "hsn_or_sac": l.get('hsn_or_sac', ''),
                "description": "Replenish negative SBE stock from Sri Bharath Electricals"
            }
            bill_line_items.append(b_item)

        # Calculate exact round off adjustment needed to match target_total
        unadjusted_tot = subtotal_calc + tax_calc
        adjustment = round(target_total - unadjusted_tot, 2)

        payload = {
            "vendor_id": VENDOR_ID,
            "bill_number": inv_no,
            "reference_number": inv_no,
            "date": inv_date,
            "branch_id": BRANCH_ID,
            "line_items": bill_line_items,
            "adjustment": adjustment,
            "adjustment_description": "Round Off"
        }

        try:
            if action == "UPDATE":
                res = client.bills.update(bill_id, payload)
                updated_bill = res.get('bill', {})
                print(f"  -> Successfully updated Bill ID {bill_id} (Total: Rs. {updated_bill.get('total'):,.2f}, Round Off: {updated_bill.get('adjustment')})")
            else:
                res = client.bills.create(payload)
                created_bill = res.get('bill', {})
                print(f"  -> Successfully created Bill ID {created_bill.get('bill_id')} (Total: Rs. {created_bill.get('total'):,.2f}, Round Off: {created_bill.get('adjustment')})")
            synced_count += 1
        except Exception as e:
            print(f"  -> Error syncing bill for {inv_no}: {e}")

    print(f"\nSuccessfully synchronized {synced_count} contra purchase bills with round off!")
    print("=== CONTRA BILL ROUND-OFF SYNCHRONIZATION COMPLETE ===")


if __name__ == "__main__":
    main()
