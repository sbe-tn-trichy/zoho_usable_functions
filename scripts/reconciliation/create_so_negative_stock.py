import logging
from zoho_usable_functions.core.auth import get_books_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing Zoho Books client...")
    client = get_books_client()

    customer_id = "1094368000052903019"  # SRI BHARATH ELECTRICALS customer contact ID
    source_location_id = "1094368000000443455"  # Sri Bharath Electricals warehouse ID
    
    # Affected items and the absolute quantities needed to reconcile negative SBE stock
    negative_stock_items = [
        {"item_id": "1094368000051614099", "qty": 12.0},
        {"item_id": "1094368000052544376", "qty": 6.0},
        {"item_id": "1094368000051638050", "qty": 12.0},
        {"item_id": "1094368000051617055", "qty": 6.0},
        {"item_id": "1094368000051614137", "qty": 6.0},
        {"item_id": "1094368000051612093", "qty": 6.0},
        {"item_id": "1094368000051642012", "qty": 48.0},
        {"item_id": "1094368000051614008", "qty": 24.0}
    ]

    item_ids = [item["item_id"] for item in negative_stock_items]
    
    logger.info("Fetching item details from Zoho Books to retrieve standard rates and names...")
    try:
        res = client.request("GET", "itemdetails", params={"item_ids": ",".join(item_ids)})
        detailed_items = res.get("items", [])
    except Exception as e:
        logger.error(f"Failed to fetch item details: {e}")
        return

    # Map item details by item_id
    details_map = {item["item_id"]: item for item in detailed_items}
    
    line_items = []
    for target in negative_stock_items:
        item_id = target["item_id"]
        qty = target["qty"]
        
        details = details_map.get(item_id)
        if not details:
            logger.warning(f"Could not find details for item ID: {item_id}")
            continue
            
        name = details.get("name", "")
        rate = float(details.get("rate", 0.0))
        
        line_items.append({
            "item_id": item_id,
            "name": name,
            "quantity": qty,
            "rate": rate,
            "location_id": source_location_id,
            "description": "Replenish negative stock in SBE from Sri Bharath Electricals"
        })
        
    if not line_items:
        logger.error("No valid line items to create Sales Order.")
        return

    # Construct the Sales Order payload
    so_payload = {
        "customer_id": customer_id,
        "location_id": source_location_id,
        "line_items": line_items,
        "notes": "Generated to transfer stock from Sri Bharath Electricals warehouse to SBE to reconcile negative stock levels."
    }

    logger.info("Creating Sales Order in Zoho Books for customer 'SRI BHARATH ELECTRICALS' (from 'Sri Bharath Electricals' location)...")
    try:
        so_res = client.sales_orders.create(so_payload)
        sales_order = so_res.get("salesorder", {})
        so_no = sales_order.get("salesorder_number")
        so_id = sales_order.get("salesorder_id")
        total = sales_order.get("total")
        logger.info(f"Successfully created Sales Order {so_no} (ID: {so_id}) with Total Amount: {total}")
        print(f"\nCreated Sales Order: {so_no}")
        print(f"Total Amount: {total}")
        print(f"Sales Order ID: {so_id}\n")
    except Exception as e:
        logger.error(f"Failed to create Sales Order: {e}")

if __name__ == "__main__":
    main()
