"""
Update unit to 'NOS' for a specified list of SKUs in Zoho Books.
Supports dry-run mode by default for verification.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging

# Quiet standard request logs
import logging
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

SKUS_TO_UPDATE = [
    "A32742204DC", "A45400E04DC", "AB3013400GF", "AB3013600GF", "AB3013800GF", "AB3013900GF",
    "AC0008901GF", "AC0009201GF", "AC1124800GF", "AC1125100GF", "AC1463700GF", "AC1537100GF",
    "AC2135600GF", "AC2136100GF", "AC2136300GF", "AC2247600GF", "AC2369500GF", "AC2544000GF",
    "AC2544100GF", "AC2544300GF", "AC2544500GF", "AC2544600GF", "AC2862600GF", "AC2862700GF",
    "AC2929000GF", "AC2953300GF", "AC2953400GF", "AC3759800GF", "AC3760000GF", "AC3760100GF",
    "AC3760200GF", "AC3760400GF", "AC3792500GF", "AC3827500GF", "AC3829100GF", "AC3855600GF",
    "AC3856000GF", "AC4437900GF", "AC4438000GF", "AC4751000GF", "AC4752400GF", "AC4787300GF",
    "AC4787400GF", "AC4787500GF", "AC4895600GF", "AC4896200GF", "AC4896600GF", "AC4897200GF",
    "AC4897300GF", "AC4897700GF", "AC4898100GF", "AC4898500GF", "AC4907400GF", "AC5037500GF",
    "AC5454300GF", "AC5471900GF", "AC5472500GF", "AC5472800GF", "AC5473100GF", "AC5760200GF",
    "AC5844000GF", "AC5999901GF", "AC6000101GF", "AC6000301GF", "AC6000501GF", "AC6000601GF",
    "AC6000701GF", "AC6002801GF", "AC6044700GF", "AC6467900GF", "AC6468000GF", "AC6468100GF",
    "AC6468200GF", "AC6468300GF", "AC6487100GF", "AC6487800GF", "AC6489300GF", "AC6489400GF",
    "AC6499400GF", "AC6533300GF", "AC6551200GF", "AC6551700GF", "AC6712300GF", "AC6712400GF",
    "AC6784800GF", "AC6842300GF", "AC6921000GF", "AC6921300GF", "AC6921800GF", "AC7044100GF",
    "AC7046400GF", "AC7046500GF", "AC7046600GF", "AC7047100GF", "AC7834800GF", "AC7941300GF",
    "AC7941400GF", "AC8141400GF", "AC8173400GF", "AC8173500GF", "AC8174000GF", "AC8175200GF",
    "AC8176400GF", "AC8177700GF", "AC8179000GF", "AC8188900GF", "AC8189000GF", "AC8312200GF",
    "AC8756900GF", "AC8757100GF", "AC8757700GF", "AC8758000GF", "AC8758300GF", "Bulb12W",
    "Bulb5W", "Bulb7W", "CD5472500GF", "Z1.50-CP-BG-DVP/-0.5/-1.0/180"
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', help='Perform updates instead of dry-run')
    args = parser.parse_args()

    is_dry_run = not args.execute
    print(f"Starting SKU unit update process. Mode: {'DRY-RUN' if is_dry_run else 'EXECUTE'}\n")

    setup_logging()
    client = get_books_client()

    not_found = []
    already_correct = []
    need_update = []
    failed_updates = []
    successful_updates = []

    total_skus = len(SKUS_TO_UPDATE)
    for idx, sku in enumerate(SKUS_TO_UPDATE, 1):
        print(f"[{idx}/{total_skus}] Processing SKU: '{sku}'...", end='', flush=True)
        try:
            # Search for item by SKU using search_text
            res = client.request('GET', 'items', params={'search_text': sku})
            items = res.get('items', [])
            
            # Find the item with exact SKU match
            matched_item = None
            for item in items:
                if item.get('sku') == sku:
                    matched_item = item
                    break
            
            if not matched_item:
                print(" NOT FOUND")
                not_found.append(sku)
                continue

            item_id = matched_item.get('item_id')
            current_unit = matched_item.get('unit')
            name = matched_item.get('name')

            if current_unit == 'NOS':
                print(f" ALREADY CORRECT ('NOS')")
                already_correct.append((sku, name))
                continue

            print(f" CURRENT UNIT: '{current_unit}' (Needs update)")
            need_update.append((sku, item_id, current_unit, name))

            if not is_dry_run:
                try:
                    # Update unit to 'NOS'
                    client.items.update(item_id, {"unit": "NOS"})
                    print(f"      -> SUCCESS: Updated to 'NOS'")
                    successful_updates.append((sku, name))
                except Exception as update_err:
                    print(f"      -> FAILED: {update_err}")
                    failed_updates.append((sku, item_id, update_err))
        except Exception as e:
            print(f" ERROR: {e}")
            failed_updates.append((sku, None, e))

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total SKUs processed: {total_skus}")
    print(f"Already correct ('NOS'): {len(already_correct)}")
    print(f"Not found in Zoho: {len(not_found)}")
    print(f"Need update: {len(need_update)}")
    
    if not is_dry_run:
        print(f"Successful updates: {len(successful_updates)}")
        print(f"Failed updates: {len(failed_updates)}")

    if not_found:
        print("\nSKUs NOT FOUND:")
        for sku in not_found:
            print(f"  - {sku}")

    if need_update:
        print(f"\nSKUs NEEDING UPDATE ({'DRY RUN ONLY' if is_dry_run else 'TO BE UPDATED'}):")
        for sku, item_id, current_unit, name in need_update:
            print(f"  - {sku} (Current: '{current_unit}', Item ID: {item_id}, Name: {name})")

    if failed_updates and not is_dry_run:
        print("\nFAILED UPDATES:")
        for sku, item_id, err in failed_updates:
            print(f"  - {sku} (Item ID: {item_id}): {err}")

    if is_dry_run and need_update:
        print("\nTo apply these changes, run with the --execute flag:")
        print("uv run python scripts/update_sku_units.py --execute")

if __name__ == "__main__":
    main()
