import argparse
import json
import sys
from typing import Any, Dict

from zoho_usable_functions.core.auth import get_books_client


def main():
    parser = argparse.ArgumentParser(description="Update Zoho Books Bill line items to use new cloned item IDs.")
    parser.add_argument("--bill-id", default="1094368000056957163", help="ID of the bill to update.")
    parser.add_argument("--execute", action="store_true", help="Actually execute the update in Zoho Books. Defaults to dry-run.")
    args = parser.parse_args()

    bill_id = args.bill_id
    execute = args.execute

    print("=" * 60)
    print("ZOHO BOOKS BILL ITEM MIGRATION")
    print(f"Bill ID: {bill_id}")
    print(f"Mode: {'EXECUTE (Live update)' if execute else 'DRY RUN (Read-only)'}")
    print("=" * 60)

    # 1. Load the clone mappings
    try:
        with open("output/clone_zeiss_results.json", "r") as f:
            clone_results = json.load(f)
    except Exception as e:
        print(f"Error loading clone mappings: {e}")
        print("Please ensure output/clone_zeiss_results.json exists and contains the migration results.")
        sys.exit(1)

    item_mapping = {}
    for item in clone_results:
        if item.get("status") == "success" and item.get("original_item_id") and item.get("new_item_id"):
            item_mapping[item["original_item_id"]] = item["new_item_id"]

    print(f"Loaded {len(item_mapping)} item mappings.")

    # 2. Fetch the target bill details
    try:
        books_client = get_books_client()
        res = books_client.bills.get(bill_id)
        bill = res.get("bill", res)
    except Exception as e:
        print(f"Error fetching bill {bill_id}: {e}")
        sys.exit(1)

    bill_number = bill.get("bill_number")
    line_items = bill.get("line_items", [])
    print(f"Successfully fetched Bill: {bill_number}")
    print(f"Total line items: {len(line_items)}")

    # 3. Construct the clean update payload
    updated_line_items = []
    change_count = 0

    # Zeiss Stock Account ID
    zeiss_stock_account_id = "1094368000000960273"

    for idx, line in enumerate(line_items, 1):
        item_id = line.get("item_id")
        sku = line.get("sku")
        name = line.get("name")
        rate = line.get("rate")
        qty = line.get("quantity")

        target_item_id = item_id
        target_account_id = line.get("account_id")
        
        if item_id in item_mapping:
            target_item_id = item_mapping[item_id]
            target_account_id = zeiss_stock_account_id
            print(f"Line {idx}: Mapped old item '{sku}' -> new item ID '{target_item_id}' (Account: Zeiss Stock)")
            change_count += 1
            
        line_item_payload = {
            "line_item_id": line.get("line_item_id"),
            "item_id": target_item_id,
            "name": name,
            "account_id": target_account_id,
            "quantity": qty,
            "rate": rate,
            "description": line.get("description", ""),
            "discount": line.get("discount", 0.0),
            "tax_id": line.get("tax_id", ""),
            "location_id": line.get("location_id", ""),
            "itc_eligibility": line.get("itc_eligibility", "eligible"),
            "hsn_or_sac": line.get("hsn_or_sac", "")
        }
        updated_line_items.append(line_item_payload)

    if change_count == 0:
        print("No items on this bill match the old item IDs list. No update needed.")
        sys.exit(0)

    print(f"\nConstructing update payload for {change_count} line item changes...")

    # We copy only the allowed and required top-level fields for PUT /bills
    update_payload = {
        "bill_number": bill_number,
        "vendor_id": bill.get("vendor_id"),
        "date": bill.get("date"),
        "due_date": bill.get("due_date"),
        "notes": bill.get("notes", ""),
        "terms": bill.get("terms", ""),
        "adjustment": bill.get("adjustment", 0.0),
        "adjustment_description": bill.get("adjustment_description", ""),
        "discount": bill.get("discount", 0.0),
        "discount_type": bill.get("discount_type", "entity_level"),
        "discount_account_id": bill.get("discount_account_id", ""),
        "is_discount_before_tax": bill.get("is_discount_before_tax", True),
        "line_items": updated_line_items
    }

    if "custom_fields" in bill and bill["custom_fields"]:
        update_payload["custom_fields"] = bill["custom_fields"]

    # 4. Perform the update
    if execute:
        print("Updating the bill in Zoho Books...")
        try:
            update_res = books_client.bills.update(bill_id, update_payload)
            print("=" * 60)
            print("UPDATE SUCCESSFUL!")
            print(f"Message: {update_res.get('message', 'Bill updated successfully')}")
            print("=" * 60)
        except Exception as e:
            print(f"Error updating bill: {e}")
            sys.exit(1)
    else:
        print("\n" + "=" * 60)
        print("DRY RUN COMPLETE")
        print(f"Would have updated Bill ID {bill_id} ({bill_number}) with {change_count} line changes.")
        print("Run with --execute to perform the actual update.")
        print("=" * 60)


if __name__ == "__main__":
    main()
