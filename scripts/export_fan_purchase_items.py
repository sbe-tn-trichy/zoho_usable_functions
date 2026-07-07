import os
import re
import csv
import logging
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

# Load config and auth from the local project packages
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.config import Config

# Initialize logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Mapping of standard sweep size conversions
MM_TO_INCH = {
    1200: 48,
    900: 36,
    1400: 56,
    400: 16,
    300: 12,
    250: 10,
    150: 6,
    600: 24,
    750: 30,
    450: 18,
    1050: 42,
    225: 9
}
INCH_TO_MM = {v: k for k, v in MM_TO_INCH.items()}

def classify_item_type(item: Dict[str, Any]) -> str:
    """
    Classify the item type based on SKU prefixes, item names, and Zoho categories.
    """
    name = item.get("item_name", "").lower()
    sku = item.get("sku", "").upper()
    cat = item.get("category_name", "")
    
    # 0. Special cases (check first)
    if "rate difference" in name:
        return "Adjustment/Service"
        
    # 1. Check SKU prefix (most reliable)
    if sku.startswith(("FCE", "FCB")) or name in ["matt blue", "matt brown", "matt smoke brown", "matt white"]:
        return "Ceiling Fan"
    elif sku.startswith("FEX") or "ef " in name:
        return "Exhaust Fan"
    elif sku.startswith("FPE") or "pf " in name:
        return "Pedestal Fan"
    elif sku.startswith(("FTA", "FT")) or "tf " in name:
        return "Table Fan"
    elif sku.startswith(("FWA", "FW")) or "wf " in name:
        return "Wall Fan"
    elif sku.startswith("FAC") or "ac " in name or "acp " in name or "acw " in name:
        return "Air Circulator"
    elif sku.startswith("HW") or "heater" in name or "wh " in name:
        return "Water Heater"
    
    # 2. Check Zoho Books category name (fallback)
    if cat == "Exhaust":
        return "Exhaust Fan"
    elif cat == "Pedestal":
        return "Pedestal Fan"
    elif cat == "Table":
        return "Table Fan"
    elif cat == "Wall":
        return "Wall Fan"
    elif cat == "Air Circulator":
        return "Air Circulator"
    elif cat == "Heater":
        return "Water Heater"
    elif "ceiling" in cat.lower():
        return "Ceiling Fan"
        
    # 3. Text checks for name
    if "exhaust" in name:
        return "Exhaust Fan"
    elif "pedestal" in name:
        return "Pedestal Fan"
    elif "table fan" in name or "table" in name:
        return "Table Fan"
    elif "wall fan" in name or "wall" in name:
        return "Wall Fan"
    elif "air circulator" in name:
        return "Air Circulator"
    elif "heater" in name or "wh " in name:
        return "Water Heater"
    elif "ceiling" in name or "fan" in name or "bldc" in name:
        return "Ceiling Fan"
        
    return "Other"

def classify_ceiling_fan_tier(item: Dict[str, Any]) -> str:
    """
    Categorize ceiling fans into tiers based on name/category/SKU prefixes.
    """
    name = item.get("item_name", "").lower()
    sku = item.get("sku", "").upper()
    cat = item.get("category_name", "").lower()
    
    if "bldc" in cat or "bldc" in name or sku.startswith("FCBLDC") or sku.startswith("FCEECE"):
        return "BLDC"
    elif "super premium" in cat or sku.startswith("FCESPS"):
        return "Super Premium"
    elif "premium" in cat or sku.startswith("FCEPRS"):
        return "Premium"
    elif "standard" in cat or sku.startswith("FCESES") and "standard" in name:
        return "Standard"
    elif "economy" in cat or sku.startswith("FCEECS"):
        return "Economy"
    elif sku.startswith("FCESES"):
        return "Standard"  # fallback for Zeal/Zoomer standard series
        
    return "Regular / Unspecified"

def extract_sweep_size(name: str, prod_type: str) -> Tuple[Any, Any]:
    """
    Extract sweep size in millimeters and inches from item name.
    """
    if prod_type in ["Water Heater", "Adjustment/Service"]:
        return None, None
        
    sweep_mm = None
    sweep_inch = None
    
    # Match MM patterns (e.g. 1200MM, 1200 mm, 1200  mm)
    mm_match = re.search(r'(\d+)\s*(?:mm|MM)', name)
    if mm_match:
        sweep_mm = int(mm_match.group(1))
        
    # Match inch patterns (e.g. 48", 48C, 48 inch, 48-inch, 12")
    inch_match = re.search(r'(\d+)\s*(?:"|inch|C\b)', name)
    if inch_match:
        sweep_inch = int(inch_match.group(1))
        
    # Try to resolve missing dimensions using standard lookup
    if sweep_mm and not sweep_inch:
        sweep_inch = MM_TO_INCH.get(sweep_mm)
    elif sweep_inch and not sweep_mm:
        sweep_mm = INCH_TO_MM.get(sweep_inch)
        
    return sweep_mm, sweep_inch

def extract_model_and_color(name: str, prod_type: str) -> Tuple[str, str]:
    """
    Extract model/series name and color variant from item name.
    """
    if prod_type == "Adjustment/Service":
        return "N/A", "N/A"
        
    # Clean type prefixes and sizes from the name to focus on model + color
    cleaned = name
    
    # 1. Remove prefixes like "1200MM 48C FAN", "36\"/900mm CF", etc.
    cleaned = re.sub(
        r'^(?:\d+(?:\.\d+)?(?:mm|MM|L|ltr|Ltr|Litre|"\/\d+mm|\"|\s*[Cc]?\s*FAN)?\s*)*\b(?:CF|PF|TF|WF|EF|ACP|ACW|FAN)\b\s*',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(r'^\d+(?:\.\d+)?(?:\s*(?:mm|MM|inch|"\/\d+mm|C|L|Ltr|Litre))\s*', '', cleaned, flags=re.IGNORECASE)
    
    # 2. Remove suffixes like (ES 1 Star), 2kW, etc.
    cleaned = re.sub(r'\s*\(\s*(?:ES|HS)?\s*(?:\d+\s*Star|BLDC)\s*\)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\b\d+kW\b', '', cleaned, flags=re.IGNORECASE)
    
    # Clean extra white spaces
    cleaned = cleaned.strip()
    
    # List of known models sorted by length descending to match longest first
    known_models = [
        "Amaze", "Zeal", "Zoomer", "Aery", "Sunami", "Fantasy", "Superb", "Freshner", "Freshobreeze",
        "Superia", "Intenso", "Aero Ultraspeed", "Aerofame", "Aerorush", "Airika", "Elanza Neo", "Elanza",
        "Eteri", "Woodart", "Oxy", "Farrata", "Aero", "Zoomer Dlx", "Zeal Classic", "Intenso Instant",
        "Sunami Oxy Farrata"
    ]
    
    model = ""
    color = ""
    
    for m in sorted(known_models, key=len, reverse=True):
        if cleaned.lower().startswith(m.lower()):
            model = name[name.lower().find(m.lower()) : name.lower().find(m.lower()) + len(m)]
            color_part = cleaned[len(m):].strip()
            # Clean common modifiers from the start of color string
            color_part = re.sub(r'^\b(?:HS|Dlx|Classic|Neo|Prime|Plus|WH)\b\s*', '', color_part, flags=re.IGNORECASE)
            color = color_part.strip()
            break
            
    if not model:
        # Heuristic fallback if model is not pre-registered
        words = cleaned.split()
        if len(words) >= 1:
            if words[0].lower() in ["matt", "bi-color", "white", "black", "brown", "blue", "grey", "silver", "gold"]:
                model = "Unspecified"
                color = cleaned
            else:
                color_words = ["white", "black", "brown", "blue", "grey", "silver", "gold", "bronze", "copper", "ivory", "cream", "yellow", "titanium", "cocoa", "choco", "ash", "luster", "smoke", "cool", "saturn", "bianco"]
                color_index = -1
                for i, w in enumerate(words):
                    if any(cw in w.lower() for cw in color_words) or w.lower() in ["matt", "mat."]:
                        color_index = i
                        break
                if color_index != -1:
                    model = " ".join(words[:color_index]).strip()
                    color = " ".join(words[color_index:]).strip()
                else:
                    if len(words) >= 2:
                        model = " ".join(words[:2])
                        color = " ".join(words[2:])
                    else:
                        model = words[0]
                        color = ""
                        
    model = model.strip() or "Unspecified"
    color = color.strip() or "Unspecified"
    
    if color.lower() in ["", "unspecified", "nil", "na"]:
        color = "Unspecified"
        
    return model, color

def main():
    print("Initializing Zoho Books client...")
    # Load dotenv from workspace root (if any)
    load_dotenv()
    
    try:
        books_client = get_books_client()
    except Exception as e:
        print(f"Authentication Error: {e}")
        return
        
    target_account_name = "Polycab Fan Purchase"
    target_account_id = "1094368000035990257"  # Default ID
    
    print("Searching for the correct Purchase Account...")
    try:
        accounts = books_client.chart_of_accounts.list_all()
        found = False
        for a in accounts:
            if a.get("account_name", "").lower() == target_account_name.lower():
                target_account_id = a["account_id"]
                target_account_name = a["account_name"]
                found = True
                print(f"Found account: {target_account_name} (ID: {target_account_id})")
                break
        if not found:
            print(f"Account '{target_account_name}' not found in Zoho Books. Falling back to default ID: {target_account_id}")
    except Exception as e:
        print(f"Warning: Could not fetch chart of accounts ({e}). Using default account ID: {target_account_id}")
        
    print(f"Fetching items for purchase account ID: {target_account_id}...")
    try:
        items = books_client.items.list_by_purchase_account(target_account_id)
        print(f"Successfully retrieved {len(items)} items.")
    except Exception as e:
        print(f"Error fetching items: {e}")
        return
        
    processed_items = []
    summary_stats = {
        "types": {},
        "tiers": {},
        "sweeps": {}
    }
    
    for item in items:
        item_id = item.get("item_id", "")
        name = item.get("item_name", "")
        sku = item.get("sku", "")
        rate = item.get("rate", 0.0)
        purchase_rate = item.get("purchase_rate", 0.0)
        hsn_or_sac = item.get("hsn_or_sac", "")
        stock_on_hand = item.get("stock_on_hand", 0.0)
        status = item.get("status", "")
        zoho_category = item.get("category_name", "")
        
        # Apply heuristics
        inferred_type = classify_item_type(item)
        inferred_tier = classify_ceiling_fan_tier(item) if inferred_type == "Ceiling Fan" else "N/A"
        sweep_mm, sweep_inch = extract_sweep_size(name, inferred_type)
        model, color = extract_model_and_color(name, inferred_type)
        
        # Extract deprecated status
        cf_dep = item.get("cf_deprecated")
        is_deprecated = cf_dep.lower() == "true" if isinstance(cf_dep, str) else bool(cf_dep)
        
        # Extract group details
        group_name = item.get("group_name", "")
        group_id = item.get("group_id", "")
        
        # Track statistics
        summary_stats["types"][inferred_type] = summary_stats["types"].get(inferred_type, 0) + 1
        if inferred_type == "Ceiling Fan":
            summary_stats["tiers"][inferred_tier] = summary_stats["tiers"].get(inferred_tier, 0) + 1
            
        sweep_str = f"{sweep_mm}mm ({sweep_inch}\")" if sweep_mm else "N/A"
        summary_stats["sweeps"][sweep_str] = summary_stats["sweeps"].get(sweep_str, 0) + 1
        
        processed_items.append({
            "Item ID": item_id,
            "Name": name,
            "SKU": sku,
            "Rate": rate,
            "Purchase Rate": purchase_rate,
            "HSN/SAC": hsn_or_sac,
            "Stock on Hand": stock_on_hand,
            "Status": status,
            "Zoho Category Name": zoho_category,
            "Inferred Type": inferred_type,
            "Inferred Tier": inferred_tier,
            "Sweep (mm)": sweep_mm if sweep_mm else "",
            "Sweep (inches)": sweep_inch if sweep_inch else "",
            "Model/Series": model,
            "Color": color,
            "Is Deprecated": is_deprecated,
            "Group Name": group_name,
            "Group ID": group_id
        })
        
    # Define outputs
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_output_dir = os.path.join(repo_root, "output")
    os.makedirs(local_output_dir, exist_ok=True)
    local_csv_path = os.path.join(local_output_dir, "fan_purchase_items.csv")
    parent_csv_path = os.path.join(os.path.dirname(repo_root), "fan_purchase_items.csv")
    
    headers = [
        "Item ID", "Name", "SKU", "Rate", "Purchase Rate", "HSN/SAC", 
        "Stock on Hand", "Status", "Zoho Category Name", "Inferred Type", 
        "Inferred Tier", "Sweep (mm)", "Sweep (inches)", "Model/Series", "Color",
        "Is Deprecated", "Group Name", "Group ID"
    ]
    
    # Separate active and deprecated items
    active_items = [item for item in processed_items if not item["Is Deprecated"]]
    deprecated_items = [item for item in processed_items if item["Is Deprecated"]]
    active_no_group_items = [item for item in active_items if not item["Group Name"]]
    
    # Save CSV helper function
    def save_csv(path: str, data: List[Dict[str, Any]], desc: str):
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(data)
            print(f"Saved {desc} to: {os.path.abspath(path)}")
        except Exception as e:
            print(f"Error saving {desc} to {path}: {e}")

    # Save local versions
    save_csv(local_csv_path, processed_items, "local full CSV")
    save_csv(os.path.join(local_output_dir, "fan_purchase_items_active.csv"), active_items, "local active CSV")
    save_csv(os.path.join(local_output_dir, "fan_purchase_items_deprecated.csv"), deprecated_items, "local deprecated CSV")
    save_csv(os.path.join(local_output_dir, "fan_purchase_items_active_no_group.csv"), active_no_group_items, "local active no-group CSV")
    
    # Save workspace versions
    parent_dir = os.path.dirname(repo_root)
    save_csv(parent_csv_path, processed_items, "workspace full CSV")
    save_csv(os.path.join(parent_dir, "fan_purchase_items_active.csv"), active_items, "workspace active CSV")
    save_csv(os.path.join(parent_dir, "fan_purchase_items_deprecated.csv"), deprecated_items, "workspace deprecated CSV")
    save_csv(os.path.join(parent_dir, "fan_purchase_items_active_no_group.csv"), active_no_group_items, "workspace active no-group CSV")
    
    # Generate Category-Group Mapping
    group_map = {}
    for item in processed_items:
        grp_name = item["Group Name"]
        grp_id = item["Group ID"]
        if not grp_name:
            continue
            
        key = (item["Zoho Category Name"], item["Inferred Type"], item["Inferred Tier"], grp_name, grp_id)
        if key not in group_map:
            group_map[key] = {
                "Zoho Category Name": item["Zoho Category Name"],
                "Inferred Type": item["Inferred Type"],
                "Inferred Tier": item["Inferred Tier"],
                "Group Name": grp_name,
                "Group ID": grp_id,
                "Total Items": 0,
                "Active Items": 0,
                "Deprecated Items": 0
            }
            
        group_map[key]["Total Items"] += 1
        if item["Is Deprecated"]:
            group_map[key]["Deprecated Items"] += 1
        else:
            group_map[key]["Active Items"] += 1
            
    map_rows = list(group_map.values())
    # Sort by Category and then Group Name
    map_rows.sort(key=lambda x: (x["Zoho Category Name"], x["Group Name"]))
    
    # Write Category-Group Map CSV
    map_headers = ["Zoho Category Name", "Inferred Type", "Inferred Tier", "Group Name", "Group ID", "Total Items", "Active Items", "Deprecated Items"]
    
    # Save local map CSV
    local_map_csv_path = os.path.join(local_output_dir, "category_group_map.csv")
    try:
        with open(local_map_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=map_headers)
            writer.writeheader()
            writer.writerows(map_rows)
        print(f"Saved local category group map to: {os.path.abspath(local_map_csv_path)}")
    except Exception as e:
        print(f"Error saving local category group map: {e}")
        
    # Save workspace map CSV
    parent_map_csv_path = os.path.join(parent_dir, "category_group_map.csv")
    try:
        with open(parent_map_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=map_headers)
            writer.writeheader()
            writer.writerows(map_rows)
        print(f"Saved workspace category group map to: {parent_map_csv_path}")
    except Exception as e:
        print(f"Error saving workspace category group map: {e}")
        
    # Also save JSON versions
    local_map_json_path = os.path.join(local_output_dir, "category_group_map.json")
    parent_map_json_path = os.path.join(parent_dir, "category_group_map.json")
    
    import json
    try:
        with open(local_map_json_path, "w", encoding="utf-8") as f:
            json.dump(map_rows, f, indent=2)
        print(f"Saved local category group map JSON to: {os.path.abspath(local_map_json_path)}")
        with open(parent_map_json_path, "w", encoding="utf-8") as f:
            json.dump(map_rows, f, indent=2)
        print(f"Saved workspace category group map JSON to: {parent_map_json_path}")
    except Exception as e:
        print(f"Error saving group map JSON: {e}")
        
    # Print statistics summary
    print("\n" + "="*50)
    print("CATEGORIZATION SUMMARY STATISTICS")
    print("="*50)
    print("\nBY PRODUCT TYPE:")
    for t, count in sorted(summary_stats["types"].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {t:20}: {count}")
        
    print("\nBY CEILING FAN TIER:")
    for tier, count in sorted(summary_stats["tiers"].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {tier:20}: {count}")
        
    print("\nBY SWEEP SIZE (All Fans):")
    for s, count in sorted(summary_stats["sweeps"].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {s:20}: {count}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
