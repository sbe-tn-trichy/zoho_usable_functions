import argparse
import sys
import os
import time
import json
import pandas as pd
from typing import Dict, Any, List

# Insert project src directory to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_inventory_client, fetch_access_tokens
from zoho_usable_functions.core.config import Config

def group_items_workaround(client, data):
    """Bypasses subclass request override to call BaseZohoClient.request with headers/data."""
    payload = {
        "JSONString": json.dumps(data)
    }
    params = {"organization_id": client.organization_id}
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    
    from zoho.base_client import BaseZohoClient
    return super(client.__class__, client).request(
        method='POST',
        endpoint='items/grouping',
        headers=headers,
        data=payload,
        params=params
    )

def main():
    parser = argparse.ArgumentParser(description="Execute grouping of ceiling fan items into variants in Zoho Inventory.")
    parser.add_argument("--execute", action="store_true", help="Perform actual update and write operations in Zoho.")
    parser.add_argument("--csv", default="output/inventory/proposed_ceiling_fan_groups.csv", help="Path to the input CSV file.")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"Error: Input CSV file '{args.csv}' not found.", file=sys.stderr)
        return

    print(f"Reading ceiling fan groupings from: {args.csv}")
    df = pd.read_csv(args.csv)
    
    # Drop empty rows/nan sku
    df = df.dropna(subset=["sku", "item_id", "proposed_group_name"])
    
    print(f"Found {len(df)} items to process.")
    if df.empty:
        print("No items to group.")
        return

    # Group records by proposed_group_name
    grouped = df.groupby("proposed_group_name")
    print(f"Distinct Item Groups to create/update: {len(grouped)}")
    for name, group in grouped:
        print(f"  - Group '{name}': {len(group)} items")

    if not args.execute:
        print("\n=== DRY RUN MODE ===")
        print("Use --execute to apply changes to Zoho Inventory.")

    try:
        tokens = fetch_access_tokens()
        client = get_inventory_client(token=tokens["inventory"], allow_books_token=True)
        
        for group_name, group_df in grouped:
            print(f"\nProcessing Group: '{group_name}' ({len(group_df)} items)")
            
            # Fetch item details first to get category_id and other fields
            items_payload = []
            group_category_id = None
            
            for _, row in group_df.iterrows():
                item_id = str(int(row["item_id"]))
                sku = row["sku"]
                new_item_name = row["new_item_name"]
                size = row["attribute_size"]
                color = row["attribute_color"]
                
                # Fetch details from Zoho
                print(f"  Fetching details for {sku} (ID: {item_id})...")
                try:
                    item_res = client.items.get(item_id)
                    item_detail = item_res.get("item", {})
                    item_category_id = item_detail.get("category_id")
                    
                    if item_category_id and not group_category_id:
                        group_category_id = item_category_id
                        
                    print(f"    Category: {item_detail.get('category_name')} (ID: {item_category_id})")
                    time.sleep(0.8) # Pacing read delay
                except Exception as err:
                    print(f"    ❌ Failed to fetch item details: {err}")
                    raise err
                
                current_name = item_detail.get("name", "")
                if current_name == new_item_name:
                    print(f"  Item {sku}: Name is already correct. Skipping name update.")
                else:
                    print(f"  Item {sku}: Update name -> '{new_item_name}' (Current: '{current_name}')")
                    if args.execute:
                        try:
                            # Update item name
                            client.items.update(item_id, {"name": new_item_name})
                            print(f"    ✅ Updated name successfully.")
                            time.sleep(2.0)  # Pacing write delay
                        except Exception as err:
                            print(f"    ❌ Failed to update name: {err}")
                            raise err
                
                items_payload.append({
                    "item_id": item_id,
                    "sku": sku,
                    "attribute_option_name1": size,
                    "attribute_option_name2": color
                })

            # 2. Group the items
            grouping_data = {
                "group_name": group_name,
                "unit": "NOS",
                "purchase_account_id": Config.FAN_PURCHASE_ACCOUNT_ID,
                "account_id": "1094368000035080815", # Sales account
                "inventory_account_id": "1094368000035130337", # Inventory Asset
                "attribute_name1": "Size",
                "attribute_name2": "Color",
                "items": items_payload
            }
            
            if group_category_id:
                grouping_data["category_id"] = group_category_id
            
            print(f"  Create Item Group '{group_name}' with {len(items_payload)} variants...")
            if args.execute:
                try:
                    res = group_items_workaround(client, grouping_data)
                    group_id = res.get("item_group", {}).get("group_id", "N/A")
                    print(f"    ✅ Successfully grouped. Group ID: {group_id}")
                    time.sleep(2.5) # Pacing write delay
                except Exception as err:
                    print(f"    ❌ Failed to group items: {err}")
                    raise err
            else:
                print("    (Dry Run: Payload constructed)")
                print(json.dumps(grouping_data, indent=4))

        print("\nAll processing complete.")
        if not args.execute:
            print("Run command with --execute to perform actual updates.")

    except Exception as e:
        print(f"\nExecution aborted due to error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
