import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from zoho_usable_functions.core.auth import get_books_client, get_inventory_client
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.inventory.item_sync import mark_inventory_items_inactive


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
    parser = argparse.ArgumentParser(description="Attempt deleting original items that were renamed to _old.")
    parser.add_argument("--execute", action="store_true", help="Actually execute the deletion in Zoho. Defaults to dry-run.")
    args = parser.parse_args()

    execute = args.execute

    print("=" * 60)
    print("ZOHO DELETE OLD ITEMS CLEANUP")
    print(f"Mode: {'EXECUTE (Live deletion)' if execute else 'DRY RUN (Read-only)'}")
    print("=" * 60)

    # 1. Load the clone results
    try:
        with open("output/clone_zeiss_results.json", "r") as f:
            clone_results = json.load(f)
    except Exception as e:
        print(f"Error loading clone mappings: {e}")
        print("Please ensure output/clone_zeiss_results.json exists.")
        sys.exit(1)

    print(f"Loaded {len(clone_results)} migration items.")

    inv_client = get_inventory_client()
    books_client = get_books_client()
    org_id = Config.ORG_ID

    deleted_count = 0
    failed_to_delete_ids = []
    failed_to_delete_details = []

    for idx, res in enumerate(clone_results, 1):
        item_id = res.get("original_item_id")
        sku = res.get("original_sku")
        renamed_sku = res.get("renamed_sku", f"{sku}_old")
        name = res.get("original_name")
        
        # Skip if item was successfully deleted in a previous run (we can check by trying to GET it first)
        try:
            get_res = inv_client.items.get(item_id)
            # Item still exists
        except Exception:
            print(f"\n[{idx}/{len(clone_results)}] Original item ID {item_id} (SKU: {renamed_sku}) was already deleted.")
            deleted_count += 1
            continue

        print(f"\n[{idx}/{len(clone_results)}] Checking original item: {name} (SKU: {renamed_sku}, ID: {item_id})")
        
        # Check usages dynamically
        usages = check_item_usages(books_client, inv_client, org_id, item_id)
        total_usages = sum(v for v in usages.values() if isinstance(v, int))
        print(f"  Existing Usages: {usages} (Total: {total_usages})")

        # Check if we expect deletion to fail based on usages
        if total_usages > 0:
            print("  -> Deletion is expected to fail due to transaction history.")

        if execute:
            if total_usages > 0:
                print("  -> Skipping delete attempt (already verified usages > 0). Marking for inactivation.")
                failed_to_delete_ids.append(item_id)
                failed_to_delete_details.append({
                    "item_id": item_id,
                    "sku": renamed_sku,
                    "name": name,
                    "reason": "Has transaction history"
                })
            else:
                print(f"  Attempting to delete item {item_id}...")
                try:
                    delete_res = inv_client.items.delete(item_id)
                    print("  -> Successfully deleted item!")
                    deleted_count += 1
                except Exception as e:
                    err_msg = str(e)
                    print(f"  -> Failed to delete: {err_msg}")
                    failed_to_delete_ids.append(item_id)
                    failed_to_delete_details.append({
                        "item_id": item_id,
                        "sku": renamed_sku,
                        "name": name,
                        "reason": err_msg
                    })
        else:
            print("  -> [DRY RUN] Would attempt to delete item.")
            if total_usages > 0:
                failed_to_delete_ids.append(item_id)
                failed_to_delete_details.append({
                    "item_id": item_id,
                    "sku": renamed_sku,
                    "name": name,
                    "reason": "Has transaction history"
                })
            else:
                deleted_count += 1

    print("\n" + "=" * 60)
    print("CLEANUP PHASE SUMMARY")
    print(f"Successfully Deleted / Already Deleted: {deleted_count}")
    print(f"Failed to Delete / Preserved: {len(failed_to_delete_ids)}")
    print("=" * 60)

    # 2. Inactivate failed items in bulk
    if failed_to_delete_ids:
        print(f"\nPhase 2: Inactivating remaining {len(failed_to_delete_ids)} items in bulk...")
        if execute:
            try:
                inactive_res = mark_inventory_items_inactive(inv_client, failed_to_delete_ids)
                print("Bulk Inactivation Response:")
                for chunk_res in inactive_res:
                    print(f"  Items: {len(chunk_res.get('item_ids', []))}, Code: {chunk_res.get('code')}, Message: {chunk_res.get('message')}")
                print("-> Successfully marked all remaining items as inactive.")
            except Exception as e:
                print(f"Error marking items inactive: {e}")
        else:
            print(f"-> [DRY RUN] Would mark {len(failed_to_delete_ids)} items as inactive.")

    # Save results
    output_path = Path("output") / "delete_old_items_results.json"
    results = {
        "deleted_count": deleted_count,
        "failed_to_delete": failed_to_delete_details,
        "inactive_marked_count": len(failed_to_delete_ids) if execute else 0
    }
    with open(output_path, "w") as out_f:
        json.dump(results, out_f, indent=2)
    print(f"\nDetails saved to: {output_path}")


if __name__ == "__main__":
    main()
