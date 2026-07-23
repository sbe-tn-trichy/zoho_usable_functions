import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from zoho_usable_functions.core.auth import get_books_client, get_inventory_client
from zoho_usable_functions.core.config import Config


def fetch_transactions_for_item(books_client: Any, inv_client: Any, item_id: str) -> List[Dict[str, Any]]:
    """Fetches details of all transactions containing the specified item ID."""
    transactions = []
    
    # 1. Books modules: mapping endpoint name, response list key, transaction number key, transaction ID key
    books_modules = [
        {"name": "invoices", "list_key": "invoices", "number_key": "invoice_number", "id_key": "invoice_id"},
        {"name": "bills", "list_key": "bills", "number_key": "bill_number", "id_key": "bill_id"},
        {"name": "salesorders", "list_key": "salesorders", "number_key": "salesorder_number", "id_key": "salesorder_id"},
        {"name": "purchaseorders", "list_key": "purchaseorders", "number_key": "purchaseorder_number", "id_key": "purchaseorder_id"},
        {"name": "creditnotes", "list_key": "creditnotes", "number_key": "creditnote_number", "id_key": "creditnote_id"},
        {"name": "vendorcredits", "list_key": "vendorcredits", "number_key": "vendorcredit_number", "id_key": "vendorcredit_id"}
    ]
    
    for mod in books_modules:
        try:
            res = books_client.request("GET", mod["name"], params={"item_id": item_id})
            records = res.get(mod["list_key"], [])
            for r in records:
                transactions.append({
                    "type": mod["name"].rstrip("s"),  # e.g., invoice, bill, salesorder
                    "number": r.get(mod["number_key"]),
                    "date": r.get("date"),
                    "id": r.get(mod["id_key"]),
                    "status": r.get("status"),
                    "vendor_or_customer": r.get("vendor_name") or r.get("customer_name") or ""
                })
        except Exception as e:
            print(f"  Error fetching {mod['name']} for item {item_id}: {e}")
            
    # 2. Inventory Adjustments
    try:
        res = inv_client.request("GET", "inventoryadjustments", params={"item_id": item_id})
        records = res.get("inventory_adjustments", [])
        for r in records:
            transactions.append({
                "type": "inventory_adjustment",
                "number": r.get("adjustment_number"),
                "date": r.get("date"),
                "id": r.get("inventory_adjustment_id"),
                "status": r.get("status"),
                "vendor_or_customer": ""
            })
    except Exception as e:
        print(f"  Error fetching adjustments for item {item_id}: {e}")
        
    return transactions


def main():
    print("=" * 60)
    print("ZEISS OLD ITEMS TRANSACTION FINDER & CSV UPDATER")
    print("=" * 60)

    # 1. Load the 17 items from output/delete_old_items_results.json
    results_path = "output/delete_old_items_results.json"
    if not os.path.exists(results_path):
        print(f"Error: {results_path} not found. Please run scripts/inventory/delete_old_items.py first.")
        sys.exit(1)
        
    with open(results_path, "r") as f:
        cleanup_results = json.load(f)
        
    failed_items = cleanup_results.get("failed_to_delete", [])
    print(f"Found {len(failed_items)} items that failed deletion (preserved/inactive).")

    if not failed_items:
        print("No items to process. Exiting.")
        sys.exit(0)

    # 2. Update the CSV in Downloads with only these 17 items
    csv_path = "/Users/vak/Downloads/Items_Zoho_Books_.csv"
    print(f"Updating CSV file: {csv_path} with {len(failed_items)} items...")
    
    try:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as csv_f:
            writer = csv.writer(csv_f)
            writer.writerow(["Item ID", "Item Name"])
            for item in failed_items:
                writer.writerow([item["item_id"], item["name"]])
        print("-> CSV file updated successfully.")
    except Exception as e:
        print(f"Error writing to CSV: {e}")
        sys.exit(1)

    # 3. Find transactions containing these items
    try:
        books_client = get_books_client()
        inv_client = get_inventory_client()
    except Exception as e:
        print(f"Error initializing Zoho clients: {e}")
        sys.exit(1)

    report = []
    
    print("\nSearching transactions for each of the 17 items...")
    for idx, item in enumerate(failed_items, 1):
        item_id = item["item_id"]
        sku = item["sku"]
        name = item["name"]
        
        print(f"[{idx}/17] Searching: {name} (SKU: {sku})")
        txs = fetch_transactions_for_item(books_client, inv_client, item_id)
        print(f"  Found {len(txs)} transactions.")
        
        report.append({
            "item_id": item_id,
            "sku": sku,
            "name": name,
            "transactions_count": len(txs),
            "transactions": txs
        })

    # Save detailed report
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "zeiss_item_transactions_report.json"
    with open(report_path, "w") as out_f:
        json.dump(report, out_f, indent=2)
        
    print("\n" + "=" * 60)
    print("TRANSACTION SEARCH COMPLETE")
    print(f"Detailed transaction report saved to: {report_path}")
    print("=" * 60)

    # Display simple summary table
    print("\nSummary of Transactions per Item:")
    print(f"{'Item Name':<35} | {'SKU':<40} | {'Total Tx':<8} | {'Breakdown':<30}")
    print("-" * 125)
    for r in report:
        breakdown_counts = {}
        for t in r["transactions"]:
            breakdown_counts[t["type"]] = breakdown_counts.get(t["type"], 0) + 1
        breakdown_str = ", ".join(f"{k}: {v}" for k, v in breakdown_counts.items())
        print(f"{r['name'][:34]:<35} | {r['sku'][:39]:<40} | {r['transactions_count']:<8} | {breakdown_str:<30}")


if __name__ == "__main__":
    main()
