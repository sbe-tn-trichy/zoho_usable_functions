import time
import logging
import concurrent.futures
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def find_negative_stock_items(
    books_client, 
    location_name: str = "SBE", 
    purchase_account_id: str = None
) -> List[Dict[str, Any]]:
    """
    Finds all items in Zoho Books/Inventory that have a negative accounting stock
    (location_stock_on_hand) in the specified location/warehouse.
    
    Args:
        books_client (ZohoBooksAPI): The authenticated Zoho Books API client.
        location_name (str): The name of the location to audit (default: 'SBE').
        purchase_account_id (str, optional): The Zoho Books purchase account ID to filter by.
        
    Returns:
        List[Dict[str, Any]]: A list of items with negative stock in that location.
    """
    logger.info(f"Retrieving items for audit at location: {location_name}...")
    try:
        if purchase_account_id:
            logger.info(f"Filtering items by purchase account ID: {purchase_account_id}")
            all_items = books_client.items.list_by_purchase_account(purchase_account_id)
        else:
            all_items = books_client.items.list_all(params={"filter_by": "ItemType.Inventory"})
    except Exception as e:
        logger.error(f"Failed to retrieve items list: {e}")
        raise e

    logger.info(f"Retrieved {len(all_items)} items. Fetching location-specific details in chunks of 200...")
    item_ids = [item["item_id"] for item in all_items if "item_id" in item]
    
    if not item_ids:
        logger.info("No items found to audit.")
        return []

    target_location_upper = location_name.strip().upper()
    chunk_size = 200
    chunks = [item_ids[i:i + chunk_size] for i in range(0, len(item_ids), chunk_size)]
    total_chunks = len(chunks)

    negative_stock_items = []
    
    # We define a helper to fetch a single chunk's details
    def fetch_chunk(chunk_idx, chunk):
        logger.debug(f"Fetching details for chunk {chunk_idx + 1}/{total_chunks} ({len(chunk)} items)...")
        detailed_items = []
        retries = 3
        for attempt in range(retries):
            try:
                # Add a tiny initial stagger to smooth out parallel startup requests
                time.sleep(chunk_idx % 5 * 0.1)
                response = books_client.request(
                    "GET", 
                    "itemdetails", 
                    params={"item_ids": ",".join(chunk)}
                )
                detailed_items = response.get("items", [])
                break
            except Exception as e:
                if "429" in str(e) and attempt < retries - 1:
                    logger.warning(f"Rate limited (429) on attempt {attempt + 1} for chunk {chunk_idx + 1}. Retrying after 5 seconds...")
                    time.sleep(5)
                else:
                    logger.error(f"Failed to fetch itemdetails for chunk {chunk_idx + 1} (attempt {attempt + 1}): {e}")
                    break
        
        # Process items for this chunk
        chunk_results = []
        for item in detailed_items:
            locations = item.get("locations", [])
            for loc in locations:
                loc_name = loc.get("location_name", "")
                if loc_name.strip().upper() == target_location_upper:
                    stock_val = loc.get("location_stock_on_hand")
                    if stock_val is not None:
                        try:
                            stock_float = float(stock_val)
                            if stock_float < 0:
                                # Custom field parsing for cf_deprecated
                                cf_deprecated = False
                                for cf in item.get("custom_fields", []):
                                    if cf.get("api_name") == "cf_deprecated":
                                        val = cf.get("value")
                                        if isinstance(val, str):
                                            cf_deprecated = val.lower() == "true"
                                        elif isinstance(val, bool):
                                            cf_deprecated = val
                                            
                                chunk_results.append({
                                    "item_id": item.get("item_id", ""),
                                    "name": item.get("name", ""),
                                    "sku": item.get("sku", ""),
                                    "stock_on_hand": item.get("stock_on_hand", 0.0),
                                    "location_stock_on_hand": stock_float,
                                    "location_name": loc_name,
                                    "status": item.get("status", ""),
                                    "is_deprecated": cf_deprecated
                                })
                        except (ValueError, TypeError) as ex:
                            logger.warning(f"Could not parse stock value '{stock_val}' for item {item.get('name')}: {ex}")
        return chunk_results

    # Use ThreadPoolExecutor to run detail fetches in parallel (max 5 workers to stay under rate limits)
    max_workers = 5
    logger.info(f"Spawning {max_workers} worker threads to download detail chunks...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_chunk = {
            executor.submit(fetch_chunk, idx, chunk): idx 
            for idx, chunk in enumerate(chunks)
        }
        
        for future in concurrent.futures.as_completed(future_to_chunk):
            idx = future_to_chunk[future]
            try:
                results = future.result()
                negative_stock_items.extend(results)
            except Exception as e:
                logger.error(f"Chunk {idx + 1} generated an exception: {e}")
                
    logger.info(f"Found {len(negative_stock_items)} items with negative stock in location '{location_name}'.")
    return negative_stock_items
