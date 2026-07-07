import os
import csv
import logging
import argparse
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.reconciliation.stock import find_negative_stock_items

# Initialize logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Find items with negative accounting stock in a specific location in Zoho.")
    parser.add_argument(
        "--location", 
        type=str, 
        default="SBE", 
        help="The name of the location to audit (default: SBE)"
    )
    parser.add_argument(
        "--purchase-account-id", 
        type=str, 
        default=None, 
        help="The Zoho Books purchase account ID to filter by (optional)"
    )
    args = parser.parse_args()

    location_name = args.location
    purchase_account_id = args.purchase_account_id
    logger.info("Initializing Zoho Books client...")
    try:
        books_client = get_books_client()
    except Exception as e:
        logger.error(f"Authentication Error: {e}")
        return

    logger.info(f"Auditing negative stock for location '{location_name}'...")
    try:
        negative_items = find_negative_stock_items(
            books_client, 
            location_name=location_name, 
            purchase_account_id=purchase_account_id
        )
    except Exception as e:
        logger.error(f"Error auditing negative stock: {e}")
        return

    if not negative_items:
        logger.info(f"No items with negative accounting stock found in location '{location_name}'.")
        return

    # Print summary table to stdout
    print("\n" + "=" * 80)
    print(f"ITEMS WITH NEGATIVE STOCK IN LOCATION '{location_name}'")
    print("=" * 80)
    print(f"{'SKU':<25} | {'Item Name':<40} | {'Stock':<10}")
    print("-" * 80)
    for item in negative_items[:30]:  # Limit print to first 30 to avoid overwhelming stdout
        print(f"{item['sku'][:25]:<25} | {item['name'][:40]:<40} | {item['location_stock_on_hand']:<10.2f}")
    if len(negative_items) > 30:
        print(f"... and {len(negative_items) - 30} more items.")
    print("=" * 80 + "\n")

    # Define outputs
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_output_dir = os.path.join(repo_root, "output")
    os.makedirs(local_output_dir, exist_ok=True)
    
    filename = f"negative_stock_{location_name.lower()}.csv"
    local_csv_path = os.path.join(local_output_dir, filename)
    parent_csv_path = os.path.join(os.path.dirname(repo_root), filename)

    headers = [
        "Item ID", "Name", "SKU", "Total Stock on Hand", 
        "Location Stock on Hand", "Location Name", "Status", "Is Deprecated"
    ]

    def save_csv(path: str, data: list, desc: str):
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for item in data:
                    writer.writerow([
                        item["item_id"],
                        item["name"],
                        item["sku"],
                        item["stock_on_hand"],
                        item["location_stock_on_hand"],
                        item["location_name"],
                        item["status"],
                        item["is_deprecated"]
                    ])
            logger.info(f"Saved {desc} to: {os.path.abspath(path)}")
        except Exception as e:
            logger.error(f"Error saving {desc} to {path}: {e}")

    save_csv(local_csv_path, negative_items, "local CSV report")
    save_csv(parent_csv_path, negative_items, "workspace CSV report")

if __name__ == "__main__":
    main()
