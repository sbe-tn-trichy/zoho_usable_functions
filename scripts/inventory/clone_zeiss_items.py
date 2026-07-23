import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from zoho_usable_functions.core.auth import get_books_client, get_inventory_client
from zoho_usable_functions.core.config import Config


def check_item_usages(books_client: Any, inv_client: Any, org_id: str, item_id: str) -> Dict[str, Any]:
    """Checks the usage of an item across invoices, bills, sales/purchase orders, credits, and adjustments."""
    usages = {}
    
    books_modules = {
        "invoices": "invoices",
        "bills": "bills",
        "salesorders": "salesorders",
        "purchaseorders": "purchaseorders",
        "creditnotes": "creditnotes",
        "vendorcredits": "vendorcredits"
    }
    
    for module_name, response_key in books_modules.items():
        try:
            res = books_client.request("GET", module_name, params={"item_id": item_id})
            items = res.get(response_key, [])
            usages[module_name] = len(items)
        except Exception as e:
            usages[module_name] = f"Error: {e}"
            
    try:
        res = inv_client.request("GET", "inventoryadjustments", params={"item_id": item_id})
        items = res.get("inventory_adjustments", [])
        usages["inventory_adjustments"] = len(items)
    except Exception as e:
        usages["inventory_adjustments"] = f"Error: {e}"
        
    return usages


def main():
    parser = argparse.ArgumentParser(description="Clone Zoho Items with Zeiss Accounts and rename old SKUs.")
    parser.add_argument("--execute", action="store_true", help="Actually modify data in Zoho Books/Inventory. Defaults to dry-run.")
    parser.add_argument("--csv", default="/Users/vak/Downloads/Items_Zoho_Books_.csv", help="Path to input items CSV.")
    args = parser.parse_args()

    execute = args.execute
    csv_path = args.csv

    print("=" * 60)
    print("ZOHO ZEISS ITEM CLONING MIGRATION")
    print(f"Mode: {'EXECUTE (Live updates)' if execute else 'DRY RUN (Read-only)'}")
    print(f"Source CSV: {csv_path}")
    print("=" * 60)

    # Initialize Clients
    try:
        books_client = get_books_client()
        inv_client = get_inventory_client()
    except Exception as e:
        print(f"Initialization Error: Failed to build API clients. {e}")
        sys.exit(1)

    org_id = Config.ORG_ID
    print(f"Organization ID: {org_id}")

    # Zeiss Accounts Config
    zeiss_sales_account_id = "1094368000000960255"
    zeiss_purchase_account_id = "1094368000000960267"
    zeiss_stock_account_id = "1094368000000960273"

    # Read items CSV
    item_ids = []
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print("Error: Empty CSV file.")
            sys.exit(1)
        
        for idx, row in enumerate(reader):
            if row and len(row) > 0 and row[0].strip():
                item_ids.append(row[0].strip())

    print(f"Found {len(item_ids)} item IDs to process.")

    results = []

    for item_idx, item_id in enumerate(item_ids, 1):
        print(f"\n[{item_idx}/{len(item_ids)}] Processing original Item ID: {item_id}")
        
        try:
            # 1. Fetch original item details
            res = inv_client.items.get(item_id)
            original_item = res.get("item", res)
            
            original_sku = original_item.get("sku", "").strip()
            original_name = original_item.get("name", "").strip()
            
            if not original_sku:
                print(f"  Warning: Item has no SKU. Skipping.")
                continue
                
            print(f"  Name: {original_name}")
            print(f"  SKU:  {original_sku}")

            # 2. Check usages
            usages = check_item_usages(books_client, inv_client, org_id, item_id)
            total_usages = sum(v for v in usages.values() if isinstance(v, int))
            print(f"  Transaction Usages: {usages} (Total: {total_usages})")

            # 3. Rename old SKU to {sku}_old
            old_sku_target = f"{original_sku}_old"
            print(f"  Renaming original SKU from '{original_sku}' to '{old_sku_target}'...")
            if execute:
                inv_client.items.update(item_id, {"sku": old_sku_target})
                print("  -> Successfully renamed original item SKU.")
            else:
                print("  -> [DRY RUN] Would update original item SKU.")

            # 4. Create new cloned item mapping to Zeiss accounts
            new_item_payload = {
                "name": original_name,
                "sku": original_sku,
                "unit": original_item.get("unit", "NOS"),
                "description": original_item.get("description", ""),
                "purchase_description": original_item.get("purchase_description", ""),
                "item_type": original_item.get("item_type", "inventory"),
                "product_type": original_item.get("product_type", "goods"),
                "rate": original_item.get("rate", 0.0),
                "purchase_rate": original_item.get("purchase_rate", 0.0),
                "account_id": zeiss_sales_account_id,
                "purchase_account_id": zeiss_purchase_account_id,
                "inventory_account_id": zeiss_stock_account_id,
                "can_be_sold": original_item.get("can_be_sold", True),
                "can_be_purchased": original_item.get("can_be_purchased", True),
                "track_inventory": original_item.get("track_inventory", True),
                "is_returnable": original_item.get("is_returnable", True),
                "inventory_valuation_method": original_item.get("inventory_valuation_method", "fifo"),
                "is_taxable": original_item.get("is_taxable", True),
                "hsn_or_sac": original_item.get("hsn_or_sac", "")
            }

            # Map tax preferences to simplified format
            tax_prefs = []
            for tp in original_item.get("item_tax_preferences", []):
                tax_prefs.append({
                    "tax_id": tp.get("tax_id"),
                    "tax_name": tp.get("tax_name"),
                    "tax_percentage": tp.get("tax_percentage"),
                    "tax_specification": tp.get("tax_specification"),
                    "tax_type": tp.get("tax_type")
                })
            if tax_prefs:
                new_item_payload["item_tax_preferences"] = tax_prefs

            print(f"  Creating new cloned item with Zeiss Accounts and clean SKU '{original_sku}'...")
            
            new_item_id = None
            if execute:
                create_res = inv_client.items.create(new_item_payload)
                created_item = create_res.get("item", create_res)
                new_item_id = created_item.get("item_id")
                print(f"  -> Successfully created new item. New Item ID: {new_item_id}")
            else:
                print("  -> [DRY RUN] Would create new cloned item.")
                new_item_id = "DRY-RUN-NEW-ID"

            results.append({
                "original_item_id": item_id,
                "original_name": original_name,
                "original_sku": original_sku,
                "renamed_sku": old_sku_target,
                "new_item_id": new_item_id,
                "usages": usages,
                "status": "success" if execute else "dry_run"
            })

        except Exception as e:
            print(f"  -> Error: {e}")
            results.append({
                "original_item_id": item_id,
                "original_sku": item_id,
                "status": "failed",
                "error": str(e)
            })

    # Save results
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    results_path = output_dir / "clone_zeiss_results.json"
    with open(results_path, "w") as out_f:
        json.dump(results, out_f, indent=2)
        
    print("\n" + "=" * 60)
    print("MIGRATION PROCESS COMPLETE")
    print(f"Results written to: {results_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
