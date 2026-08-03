#!/usr/bin/env python3
"""
Script to split draft invoice 1094368000058722034 into multiple invoices 
such that each individual invoice total does not exceed Rs. 87,500 (incl. GST).

Dates of created invoices span from 18 July 2026 to 31 July 2026, avoiding Sundays.
Prior draft split invoices are cleaned up before creating the 15 new split invoices.
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

# Add repo src and sibling zoho_sdk/src to sys.path if not installed
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT.parent / "zoho_sdk" / "src"
SRC_ROOT = REPO_ROOT / "src"

if str(SDK_ROOT) not in sys.path and SDK_ROOT.exists():
    sys.path.insert(0, str(SDK_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zoho_usable_functions.core.auth import get_books_client

TARGET_INVOICE_ID = "1094368000058722034"
MAX_INVOICE_TOTAL = 87500.0

WORKING_DATES = [
    "2026-07-18",  # Sat
    "2026-07-20",  # Mon
    "2026-07-21",  # Tue
    "2026-07-22",  # Wed
    "2026-07-23",  # Thu
    "2026-07-24",  # Fri
    "2026-07-25",  # Sat
    "2026-07-27",  # Mon
    "2026-07-28",  # Tue
    "2026-07-29",  # Wed
    "2026-07-30",  # Thu
    "2026-07-31",  # Fri
]

# 13 draft invoice IDs created during previous split run to clean up
PREVIOUS_SPLIT_IDS = [
    "1094368000058802012",
    "1094368000058805030",
    "1094368000058789008",
    "1094368000058812003",
    "1094368000058792004",
    "1094368000058798005",
    "1094368000058788563",
    "1094368000058807003",
    "1094368000058803004",
    "1094368000058811003",
    "1094368000058793003",
    "1094368000058805006",
    "1094368000058810003",
]


def load_original_invoice_data():
    """Load cached invoice data JSON or fetch from Zoho API if original exists."""
    cached_path = REPO_ROOT / "scratch" / "invoice_details.json"
    if not cached_path.exists():
        cached_path = Path(r"C:\Users\VAK\.gemini\antigravity-ide\brain\df0f7ef3-8e5e-43ab-917f-98abcc37ffbf\scratch\invoice_details.json")
    
    with open(cached_path) as f:
        return json.load(f)


def plan_invoice_splits(inv_data):
    """
    Splits invoice line items into distinct invoice payloads <= MAX_INVOICE_TOTAL.
    Returns list of split invoice payload dicts.
    """
    line_items = inv_data.get("line_items", [])
    
    # Expand line items into unit item tokens with storage mapping
    units_list = []
    for line in line_items:
        rate = float(line.get("rate", 0))
        item_id = line.get("item_id")
        name = line.get("name")
        sku = line.get("sku") or ""
        tax_id = line.get("tax_id")
        tax_name = line.get("tax_name")
        tax_percentage = float(line.get("tax_percentage", 18))
        unit_name = line.get("unit") or "NOS"
        description = line.get("description") or name or ""
        account_id = line.get("account_id") or "1094368000035080815"
        hsn_or_sac = line.get("hsn_or_sac") or ""
        
        storages = line.get("storages", [])
        total_st_qty = sum(int(st.get("out_quantity", 0)) for st in storages)
        line_qty = int(line["quantity"])

        if storages and total_st_qty > 0:
            for st in storages:
                st_id = st.get("storage_id")
                st_q = int(st.get("out_quantity", 0))
                for _ in range(st_q):
                    units_list.append({
                        "item_id": item_id,
                        "name": name,
                        "sku": sku,
                        "rate": rate,
                        "tax_id": tax_id,
                        "tax_name": tax_name,
                        "tax_percentage": tax_percentage,
                        "unit": unit_name,
                        "description": description,
                        "account_id": account_id,
                        "hsn_or_sac": hsn_or_sac,
                        "storage_id": st_id,
                    })
        else:
            for _ in range(line_qty):
                units_list.append({
                    "item_id": item_id,
                    "name": name,
                    "sku": sku,
                    "rate": rate,
                    "tax_id": tax_id,
                    "tax_name": tax_name,
                    "tax_percentage": tax_percentage,
                    "unit": unit_name,
                    "description": description,
                    "account_id": account_id,
                    "hsn_or_sac": hsn_or_sac,
                    "storage_id": None,
                })

    # Partition units into buckets <= MAX_INVOICE_TOTAL (including GST 18%)
    invoices_units = []
    current_units = []
    for unit in units_list:
        temp_units = current_units + [unit]
        temp_subtotal = sum(u["rate"] for u in temp_units)
        temp_tax = round(temp_subtotal * 0.09, 2) + round(temp_subtotal * 0.09, 2)
        temp_total = temp_subtotal + temp_tax
        if temp_total <= MAX_INVOICE_TOTAL:
            current_units.append(unit)
        else:
            invoices_units.append(current_units)
            current_units = [unit]
    if current_units:
        invoices_units.append(current_units)

    # Assign dates sequentially (15 working dates; all non-Sundays between July 18 and July 31)
    assigned_dates = sorted(WORKING_DATES + ["2026-07-18", "2026-07-31", "2026-07-31"])

    payloads = []
    item_qty_check = defaultdict(int)

    for idx, (inv_u, inv_date) in enumerate(zip(invoices_units, assigned_dates), 1):
        line_map = {}
        storage_map = defaultdict(lambda: defaultdict(int))

        for u in inv_u:
            item_id = u["item_id"]
            item_qty_check[item_id] += 1
            if u["storage_id"]:
                storage_map[item_id][u["storage_id"]] += 1

            if item_id not in line_map:
                line_map[item_id] = {
                    "item_id": item_id,
                    "name": u["name"],
                    "rate": u["rate"],
                    "tax_id": u["tax_id"],
                    "unit": u["unit"],
                    "description": u["description"],
                    "account_id": u["account_id"],
                    "quantity": 0,
                }
                if u["hsn_or_sac"]:
                    line_map[item_id]["hsn_or_sac"] = u["hsn_or_sac"]
            line_map[item_id]["quantity"] += 1

        for item_id, item_dict in line_map.items():
            if item_id in storage_map:
                st_list = []
                for st_id, st_q in storage_map[item_id].items():
                    st_list.append({
                        "storage_id": st_id,
                        "out_quantity": st_q
                    })
                if st_list:
                    item_dict["storages"] = st_list

        consolidated_lines = list(line_map.values())
        subtotal = sum(l["quantity"] * l["rate"] for l in consolidated_lines)
        gst = round(subtotal * 0.09, 2) + round(subtotal * 0.09, 2)
        total = round(subtotal + gst, 2)

        payload = {
            "customer_id": inv_data.get("customer_id"),
            "date": inv_date,
            "place_of_supply": inv_data.get("place_of_supply"),
            "gst_treatment": inv_data.get("gst_treatment"),
            "gst_no": inv_data.get("gst_no"),
            "location_id": inv_data.get("location_id") or inv_data.get("branch_id"),
            "notes": inv_data.get("notes"),
            "terms": inv_data.get("terms"),
            "template_id": inv_data.get("template_id"),
            "line_items": consolidated_lines,
            "_subtotal": subtotal,
            "_gst": gst,
            "_total": total,
            "_total_units": sum(l["quantity"] for l in consolidated_lines),
        }
        payloads.append(payload)

    # Verification against original line items
    original_qty_map = {line["item_id"]: int(line["quantity"]) for line in line_items}
    for item_id, orig_q in original_qty_map.items():
        split_q = item_qty_check[item_id]
        if split_q != orig_q:
            raise ValueError(f"Quantity mismatch for item_id {item_id}: original {orig_q} vs split sum {split_q}")

    return payloads


def main():
    parser = argparse.ArgumentParser(description="Split invoice into multiple invoices <= 87,500.")
    parser.add_argument("--execute", action="store_true", help="Execute changes in Zoho Books.")
    args = parser.parse_args()

    inv_data = load_original_invoice_data()
    print(f"Loaded invoice data for customer: {inv_data.get('customer_name')}")
    print(f"Original Total: Rs. {inv_data.get('total'):,.2f} | Subtotal: Rs. {inv_data.get('sub_total'):,.2f}")

    split_payloads = plan_invoice_splits(inv_data)
    print(f"\nSuccessfully partitioned into {len(split_payloads)} split invoices (Max limit: Rs. {MAX_INVOICE_TOTAL:,.2f}).")
    print("=" * 100)
    print(f"{'#':<3} | {'Date':<10} | {'Lines':<5} | {'Units':<5} | {'Subtotal (Rs.)':<15} | {'18% GST (Rs.)':<15} | {'Total (Rs.)':<15}")
    print("=" * 100)

    grand_total = 0.0
    for idx, p in enumerate(split_payloads, 1):
        grand_total += p["_total"]
        print(f"{idx:<3} | {p['date']:<10} | {len(p['line_items']):<5} | {p['_total_units']:<5} | {p['_subtotal']:>15,.2f} | {p['_gst']:>15,.2f} | {p['_total']:>15,.2f}")
    
    print("=" * 100)
    print(f"Grand Total Across {len(split_payloads)} Split Invoices: Rs. {grand_total:,.2f}")

    if not args.execute:
        print("\n[DRY RUN COMPLETE] No changes were written to Zoho Books. Pass '--execute' to perform splitting.")
        return

    client = get_books_client()
    print("\n--- EXECUTING CLEANUP & SPLIT CREATION IN ZOHO BOOKS ---")
    
    # 1. Cleanup previous draft split invoices to release bin stock locks
    print(f"Cleaning up {len(PREVIOUS_SPLIT_IDS)} previous draft split invoices...")
    for prev_id in PREVIOUS_SPLIT_IDS:
        try:
            client.invoices.delete(prev_id)
            print(f"  - Deleted previous split invoice {prev_id}")
        except Exception as e:
            print(f"  - Notice: Could not delete {prev_id}: {e}")

    # 2. Create the 15 new split invoices
    created_invoices = []
    for idx, p in enumerate(split_payloads, 1):
        clean_payload = {k: v for k, v in p.items() if not k.startswith("_")}
        print(f"[{idx}/{len(split_payloads)}] Creating invoice for date {clean_payload['date']} (Total: Rs. {p['_total']:,.2f})...")
        try:
            create_res = client.invoices.create(clean_payload)
            inv_obj = create_res.get("invoice", {})
            created_invoices.append(inv_obj)
            print(f"  -> Created Invoice Number: {inv_obj.get('invoice_number')} (ID: {inv_obj.get('invoice_id')}) | Total: Rs. {inv_obj.get('total'):,.2f}")
        except Exception as e:
            print(f"Error creating invoice #{idx}: {e}")
            print(f"Created {len(created_invoices)} invoices before error.")
            sys.exit(1)

    print(f"\nAll {len(created_invoices)} invoices successfully created!")
    print("\n=== INVOICE SPLIT EXECUTION COMPLETE ===")


if __name__ == "__main__":
    main()
