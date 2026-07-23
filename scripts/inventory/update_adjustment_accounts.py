#!/usr/bin/env python3
"""
Audit and update Zoho Inventory adjustments with incorrect accounts.
Matches B&L warehouse to Stock Transfer BL and others to Stock Transfer Account.
Excludes zero-effect adjustments.
"""

import argparse
import sys
import time
from typing import Dict, Any, List

from zoho_usable_functions.core.auth import get_inventory_client, fetch_access_tokens

# Constants
ACCOUNT_STOCK_TRANSFER_ACCOUNT = "1094368000044177615"  # Stock Transfer Account (SBE/Others)
ACCOUNT_STOCK_TRANSFER_BL = "1094368000057013029"       # Stock Transfer BL (B&L)

ACCOUNT_NAMES = {
    ACCOUNT_STOCK_TRANSFER_ACCOUNT: "Stock Transfer Account",
    ACCOUNT_STOCK_TRANSFER_BL: "Stock Transfer BL"
}

WAREHOUSE_BL_ID = "1094368000006367844"  # B&L Warehouse ID


def map_warehouse_to_account(warehouse_id: str, warehouse_name: str) -> str:
    """Maps a warehouse ID or name to the correct target adjustment account ID."""
    name_lower = (warehouse_name or "").lower()
    if warehouse_id == WAREHOUSE_BL_ID or "b&l" in name_lower or "lonavala" in name_lower:
        return ACCOUNT_STOCK_TRANSFER_BL
    return ACCOUNT_STOCK_TRANSFER_ACCOUNT


def request_with_retry(client: Any, method: str, url: str, **kwargs) -> Any:
    """Helper to perform requests with retry logic on encountering rate limits (HTTP 429) or token expiration (HTTP 401)."""
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            res = client.request(method, url, **kwargs)
            if isinstance(res, dict) and (res.get("code") == 43 or "exceeded the maximum" in str(res.get("message", "")).lower()):
                print(f"\n  Rate limit hit (code {res.get('code')}). Sleeping for 30 seconds (attempt {attempt}/{max_retries})...")
                time.sleep(30)
                continue
            return res
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "unauthorized" in err_str.lower() or "invalid_token" in err_str.lower() or "not authorized" in err_str.lower() or "code:57" in err_str.lower() or "code\":57" in err_str.lower():
                print(f"\n  Access token expired (401). Refreshing token and retrying (attempt {attempt}/{max_retries})...")
                try:
                    new_tokens = fetch_access_tokens()
                    new_token = new_tokens.get("inventory") or new_tokens.get("books")
                    if new_token:
                        client.access_token = new_token
                        # Update the authorization header in kwargs if it was passed explicitly
                        if "headers" in kwargs and isinstance(kwargs["headers"], dict):
                            kwargs["headers"]["Authorization"] = f"Zoho-oauthtoken {new_token}"
                except Exception as token_err:
                    print(f"  Failed to refresh token: {token_err}")
                time.sleep(2)
                continue
            elif "429" in err_str or "rate" in err_str.lower() or "blocked" in err_str.lower() or "too many" in err_str.lower() or "code:43" in err_str.lower():
                print(f"\n  Rate limit exception. Sleeping for 30 seconds (attempt {attempt}/{max_retries})...")
                time.sleep(30)
                continue
            raise e
    # Final retry before letting exception propagate
    return client.request(method, url, **kwargs)


def get_adjustment_details(client: Any, adj_id: str) -> Dict[str, Any]:
    """Retrieves full details for a single inventory adjustment."""
    res = request_with_retry(client, "GET", f"inventoryadjustments/{adj_id}")
    return res.get("inventory_adjustment", {})


def update_adjustment_account(client: Any, adj_id: str, current_adj: Dict[str, Any], target_account_id: str) -> bool:
    """
    Attempts to update the adjustment account ID of an inventory adjustment.
    Uses the full payload to ensure all required fields are preserved.
    """
    # Build payload containing necessary details to avoid API validation errors
    # Note: For adjustments, Zoho Inventory API expects specific fields
    payload = {
        "date": current_adj.get("date"),
        "adjustment_type": current_adj.get("adjustment_type"),
        "adjustment_account_id": target_account_id,
        "reason": current_adj.get("reason"),
        "description": current_adj.get("description"),
        "reference_number": current_adj.get("reference_number"),
    }
    
    # Map line items
    line_items = []
    for item in current_adj.get("line_items", []):
        line_items.append({
            "line_item_id": item.get("line_item_id"),
            "item_id": item.get("item_id"),
            "quantity_adjusted": item.get("quantity_adjusted"),
            "value_adjusted": item.get("value_adjusted"),
            "price": item.get("price"),
            "location_id": item.get("location_id"),
            "description": item.get("description"),
            "adjustment_account_id": target_account_id,
            "batches": item.get("batches", []),
        })
    
    payload["line_items"] = line_items

    try:
        # Send update request
        # Endpoint: PUT inventoryadjustments/{adjustment_id}
        res = request_with_retry(client, "PUT", f"inventoryadjustments/{adj_id}", json=payload)
        code = res.get("code")
        if code == 0:
            time.sleep(2.0)  # Safe delay to prevent rate limits
            return True
        else:
            print(f"  Error updating {adj_id}: {res.get('message')}")
            return False
    except Exception as e:
        print(f"  Exception updating {adj_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Audit and update Zoho Inventory adjustment accounts.")
    parser.add_argument("--execute", action="store_true", help="Perform the actual updates in Zoho Inventory.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of adjustments audited (for testing).")
    parser.add_argument("--max-updates", type=int, default=None, help="Limit the maximum number of adjustments to actually update.")
    parser.add_argument("--from-csv", action="store_true", help="Read target adjustments to update directly from the output CSV file.")
    args = parser.parse_args()

    try:
        # 1. Fetch access tokens and initialize client
        tokens = fetch_access_tokens()
        client = get_inventory_client(token=tokens["inventory"], allow_books_token=True)
        
        to_update = []
        
        if args.from_csv:
            import os
            import pandas as pd
            csv_path = "output/inventory_adjustments_to_update.csv"
            if not os.path.exists(csv_path):
                print(f"Error: CSV file {csv_path} does not exist.")
                return
            
            print(f"Reading target adjustments from {csv_path}...")
            df = pd.read_csv(csv_path)
            if df.empty:
                print("CSV file is empty.")
                return
                
            unique_targets = df.drop_duplicates(subset=["adjustment_id"])
            print(f"Loaded {len(unique_targets)} adjustments from CSV.")
            
            # Apply limit if specified
            if args.limit is not None:
                print(f"Limiting audit to first {args.limit} adjustments from CSV.")
                unique_targets = unique_targets.iloc[:args.limit]
                
            print("\nAuditing adjustments listed in CSV...")
            for idx, (_, row) in enumerate(unique_targets.iterrows(), 1):
                adj_id = str(row["adjustment_id"])
                target_acct_id = str(row["proposed_account_id"])
                target_acct_name = str(row["proposed_account_name"])
                sys.stdout.write(f"\rRetrieving details {idx}/{len(unique_targets)} (ID: {adj_id})...")
                sys.stdout.flush()
                
                try:
                    full_adj = get_adjustment_details(client, adj_id)
                    time.sleep(0.8)  # Safe delay to prevent rate limits
                    current_acct_id = full_adj.get("adjustment_account_id")
                    current_acct_name = full_adj.get("adjustment_account_name")
                    
                    if current_acct_id != target_acct_id:
                        warehouse_name = full_adj.get("warehouse_name")
                        if not warehouse_name and full_adj.get("line_items"):
                            warehouse_name = full_adj["line_items"][0].get("warehouse_name") or full_adj["line_items"][0].get("location_name")
                            
                        to_update.append({
                            "adjustment_id": adj_id,
                            "date": full_adj.get("date"),
                            "reason": full_adj.get("reason"),
                            "warehouse_name": warehouse_name or "Unknown",
                            "current_account_id": current_acct_id,
                            "current_account_name": current_acct_name,
                            "target_account_id": target_acct_id,
                            "target_account_name": target_acct_name,
                            "total": full_adj.get("total"),
                            "full_adj_data": full_adj
                        })
                except Exception as e:
                    print(f"\n  Error auditing adjustment {adj_id}: {e}")
                    
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()
        else:
            print("Fetching all inventory adjustments from Zoho...")
            all_adjustments = client.inventory_adjustments.list_all(resource_key="inventory_adjustments")
            print(f"Total adjustments listed: {len(all_adjustments)}")
            
            # 2. Filter adjustments that are non-zero
            non_zero_adjustments = []
            for adj in all_adjustments:
                total = float(adj.get("total") or 0.0)
                date = adj.get("date", "")
                if total > 0.0 and ("2025-04-01" <= date <= "2026-03-31"):
                    non_zero_adjustments.append(adj)
                    
            print(f"Found {len(non_zero_adjustments)} non-zero adjustments between 2025-04-01 and 2026-03-31.")
            
            # Apply limit if specified
            if args.limit is not None:
                print(f"Limiting audit to first {args.limit} non-zero adjustments.")
                non_zero_adjustments = non_zero_adjustments[:args.limit]
                
            # 3. Audit each non-zero adjustment
            print("\nAuditing adjustments to check account associations...")
            for idx, adj in enumerate(non_zero_adjustments, 1):
                adj_id = adj["inventory_adjustment_id"]
                sys.stdout.write(f"\rRetrieving details {idx}/{len(non_zero_adjustments)} (ID: {adj_id})...")
                sys.stdout.flush()
                
                try:
                    full_adj = get_adjustment_details(client, adj_id)
                    time.sleep(0.8)  # Safe delay to prevent rate limits
                    current_acct_id = full_adj.get("adjustment_account_id")
                    current_acct_name = full_adj.get("adjustment_account_name")
                    
                    # Check for zero-effect adjustments (total in detail is 0.0)
                    adj_total = float(full_adj.get("total") or 0.0)
                    if adj_total == 0.0:
                        continue
                    
                    # Check warehouse / location to determine expected account
                    warehouse_id = full_adj.get("warehouse_id")
                    warehouse_name = full_adj.get("warehouse_name")
                    
                    # If warehouse_id not in main level, check first line item
                    if not warehouse_id and full_adj.get("line_items"):
                        warehouse_id = full_adj["line_items"][0].get("warehouse_id") or full_adj["line_items"][0].get("location_id")
                        warehouse_name = full_adj["line_items"][0].get("warehouse_name") or full_adj["line_items"][0].get("location_name")
                    
                    expected_acct_id = map_warehouse_to_account(warehouse_id, warehouse_name)
                    expected_acct_name = ACCOUNT_NAMES.get(expected_acct_id, "Unknown")
                    
                    if current_acct_id != expected_acct_id:
                        to_update.append({
                            "adjustment_id": adj_id,
                            "date": full_adj.get("date"),
                            "reason": full_adj.get("reason"),
                            "warehouse_name": warehouse_name or "Unknown",
                            "current_account_id": current_acct_id,
                            "current_account_name": current_acct_name,
                            "target_account_id": expected_acct_id,
                            "target_account_name": expected_acct_name,
                            "total": full_adj.get("total"),
                            "full_adj_data": full_adj
                        })
                except Exception as e:
                    print(f"\n  Error auditing adjustment {adj_id}: {e}")
                    
            # Clear status line
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()
            
        print(f"Audit complete. Found {len(to_update)} adjustments requiring account updates.\n")
        
        if not to_update:
            print("No adjustments require updates. All non-zero adjustments are correctly associated.")
            return
            
        # Save to CSV (detailed line-item level)
        import os
        import pandas as pd
        os.makedirs("output", exist_ok=True)
        csv_path = "output/inventory_adjustments_to_update.csv"
        
        csv_rows = []
        for item in to_update:
            full_adj = item["full_adj_data"]
            for line in full_adj.get("line_items", []):
                csv_rows.append({
                    "adjustment_id": item["adjustment_id"],
                    "date": item["date"],
                    "reason": item["reason"],
                    "warehouse": item["warehouse_name"],
                    "adjustment_total": item["total"],
                    "item_sku": line.get("sku"),
                    "item_name": line.get("name"),
                    "quantity_adjusted": line.get("quantity_adjusted"),
                    "item_total": line.get("item_total"),
                    "current_account_name": item["current_account_name"],
                    "current_account_id": item["current_account_id"],
                    "proposed_account_name": item["target_account_name"],
                    "proposed_account_id": item["target_account_id"]
                })
        
        df = pd.DataFrame(csv_rows)
        df.to_csv(csv_path, index=False)
        print(f"Saved detailed audit list (line items) of adjustments to update to: {csv_path}\n")
            
        # Display adjustments requiring update (truncated view)
        print(f"{'Adjustment ID':<20} | {'Date':<10} | {'Warehouse':<15} | {'Current Account':<25} | {'Proposed Account':<25} | {'Total':<10}")
        print("-" * 115)
        for item in to_update[:15]:
            print(f"{item['adjustment_id']:<20} | {item['date']:<10} | {item['warehouse_name']:<15} | {item['current_account_name']:<25} | {item['target_account_name']:<25} | {item['total']:<10}")
        if len(to_update) > 15:
            print(f"... and {len(to_update) - 15} more rows (see saved CSV file) ...")
            
        # 4. Perform updates if execute flag is set
        if args.execute:
            if args.max_updates is not None:
                print(f"Limiting execution to first {args.max_updates} adjustments needing updates.")
                to_update = to_update[:args.max_updates]
            print(f"\nProceeding to update {len(to_update)} adjustments...")
            success_count = 0
            for idx, item in enumerate(to_update, 1):
                adj_id = item["adjustment_id"]
                target_id = item["target_account_id"]
                target_name = item["target_account_name"]
                
                print(f"[{idx}/{len(to_update)}] Updating adjustment {adj_id} to '{target_name}'...")
                success = update_adjustment_account(client, adj_id, item["full_adj_data"], target_id)
                if success:
                    print(f"  Success!")
                    success_count += 1
                else:
                    print(f"  Failed!")
                    
            print(f"\nUpdate process finished. Successfully updated {success_count}/{len(to_update)} adjustments.")
        else:
            print("\nDry-run completed. To apply these changes, run the command with the '--execute' flag.")
            
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
