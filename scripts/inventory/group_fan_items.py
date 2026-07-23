import argparse
import sys
import os
import re
import pandas as pd
from typing import Dict, Any, List, Tuple

# Insert project src directory to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_inventory_client, fetch_access_tokens
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.inventory.item_sync import fetch_items_for_purchase_account

# List of known fan models to match against
MODEL_FAMILIES = sorted([
    "AERY", "FRESHOBREEZE", "FRESHNER NEO", "AIROFRESH", "FRESHNER", "SILENCIO MINI", 
    "AEROBLISS", "ZOOMER PRIME", "ZOOMER DLX", "ZOOMER", "ZEAL", "AMAZE", "ELANZA NEO", 
    "SILENCIO MINI LED", "VITAL PETAL", "ELEGANZ PEARL", "SUPERIA", "WHOOSH", "FRESHLY",
    "FRESH-ON", "FANTASY CABIN", "AIROFRESH NEO", "SUNAMI", "AFFECIENTE NEO", "AIRIKA", 
    "JUNO", "AEROFAME", "AERORUSH", "AEROGLAM", "AMBIANCE", "ELANZA PRIME", "AERO ULTRASPEED",
    "SILENCIO CRUISER PRIME", "SILENCIO CRUISER"
], key=len, reverse=True)

def clean_item_name(name: str) -> str:
    """Normalize spaces and casing in names."""
    return re.sub(r'\s+', ' ', name).strip()

def extract_attributes(name: str, sku: str) -> Tuple[str, str, str, str, str, str]:
    """
    Parses an item name and SKU to extract proposed group name and attributes:
    - proposed_group_name (e.g. Aerobliss ES)
    - color (e.g. Cocoa Bronze)
    - speed (e.g. HS, NS, Standard)
    - size (e.g. 1200mm, 400mm)
    - fan_type (e.g. CF, EF, WF, PF, TF, WH, Other)
    - new_item_name (e.g. 48"/1200mm CF Aerobliss Cocoa Bronze (ES 1 Star))
    """
    name_upper = name.upper()
    # Clean string to put spaces before units so numbers are standalone words
    name_clean = re.sub(r'(\d+)\s*(MM|INCH|C\b|L\b|\")\s*', r' \1 \2 ', name_upper)
    
    # Helper to check if a size number is standalone in the name
    def has_size(num_str: str) -> bool:
        return bool(re.search(rf'\b{num_str}\b', name_clean))

    # 1. Standardize size mapping
    size_attr = "Standard"
    size_prefix = ""
    if has_size("1400") or has_size("56"):
        size_attr = "1400mm"
        size_prefix = '56"/1400mm'
    elif has_size("1200") or has_size("48"):
        size_attr = "1200mm"
        size_prefix = '48"/1200mm'
    elif has_size("900") or has_size("36"):
        size_attr = "900mm"
        size_prefix = '36"/900mm'
    elif has_size("600") or has_size("24"):
        size_attr = "600mm"
        size_prefix = '24"/600mm'
    elif has_size("450") or has_size("18"):
        size_attr = "450mm"
        size_prefix = '18"/450mm'
    elif has_size("400") or has_size("16"):
        size_attr = "400mm"
        size_prefix = '16"/400mm'
    elif has_size("380") or has_size("15"):
        size_attr = "380mm"
        size_prefix = '15"/380mm'
    elif has_size("300") or has_size("12"):
        size_attr = "300mm"
        size_prefix = '12"/300mm'
    elif has_size("250") or has_size("10"):
        size_attr = "250mm"
        size_prefix = '10"/250mm'
    elif has_size("225") or has_size("9"):
        size_attr = "225mm"
        size_prefix = '9"/225mm'
    elif has_size("200") or has_size("8"):
        size_attr = "200mm"
        size_prefix = '8"/200mm'
    elif has_size("150") or has_size("6"):
        size_attr = "150mm"
        size_prefix = '6"/150mm'
    elif has_size("100") or has_size("4"):
        size_attr = "100mm"
        size_prefix = '4"/100mm'
    elif has_size("500") or has_size("20"):
        size_attr = "500mm"
        size_prefix = '20"/500mm'
    elif has_size("10") and "L" in name_upper:
        size_attr = "10L"
        size_prefix = "10L"
    elif has_size("15") and "L" in name_upper:
        size_attr = "15L"
        size_prefix = "15L"
        
    # 2. Type mapping based on SKU prefix and name keywords
    sku_upper = sku.upper() if sku else ""
    if sku_upper.startswith("FC"):
        fan_type = "CF"
    elif sku_upper.startswith("FE"):
        fan_type = "EF"
    elif sku_upper.startswith("FW") or " WF " in f" {name_upper} " or "WALL" in name_upper:
        fan_type = "WF"
    elif sku_upper.startswith("FP") or " PF " in f" {name_upper} " or "PEDESTAL" in name_upper:
        fan_type = "PF"
    elif sku_upper.startswith("FT") or " TF " in f" {name_upper} " or "TABLE" in name_upper:
        fan_type = "TF"
    elif sku_upper.startswith("HW") or "HWHS" in name_upper or "WATER HEATER" in name_upper or " WH " in f" {name_upper} ":
        fan_type = "WH"
    else:
        fan_type = "Other"
        
    # 3. Model family mapping
    model_family = "Other Fan"
    for model in MODEL_FAMILIES:
        if model in name_upper:
            model_family = model
            break

    if fan_type == "WH":
        model_family = "Superia" if "SUPERIA" in name_upper else "Water Heater"
        
    # 4. Speed mapping
    speed = "Standard"
    if " HS " in f" {name_upper} " or "(HS" in name_upper:
        speed = "HS"
    elif " NS " in f" {name_upper} " or "(NS" in name_upper:
        speed = "NS"

    # 5. Extract Suffix (like ES 1 STAR, 1 STAR, etc.)
    suffix_parts = []
    
    # Check for "ES 1 STAR", "ES 5 STAR", etc.
    es_star_match = re.search(r'\bES\s*(\d+)\s*STAR\b', name_upper)
    if es_star_match:
        suffix_parts.append(f"ES {es_star_match.group(1)} Star")
    else:
        # Check for standard star rating
        star_match = re.search(r'\b(\d+)\s*STAR\b', name_upper)
        if star_match:
            suffix_parts.append(f"{star_match.group(1)} Star")
            
        # Check for ES alone (if not matched with Star)
        if re.search(r'\bES\b', name_upper) and not es_star_match:
            suffix_parts.append("ES")
            
    if re.search(r'\bBLDC\b', name_upper):
        suffix_parts.append("BLDC")
        
    if re.search(r'\bHS\b', name_upper) and fan_type == "CF":
        suffix_parts.append("HS")
    elif re.search(r'\bNS\b', name_upper) and fan_type == "CF":
        suffix_parts.append("NS")

    suffix = f" ({' '.join(suffix_parts)})" if suffix_parts else ""

    # 6. Extract Color using regex word boundaries
    clean_target = name_upper
    
    # Strip star rating patterns
    clean_target = re.sub(r'\b\d+\s*STAR\b', '', clean_target)
    clean_target = re.sub(r'\bES\s+\d+\s*STAR\b', '', clean_target)
    clean_target = re.sub(r'\bHS\s+\d+\s*STAR\b', '', clean_target)
    
    # Remove specific water heater phrases
    clean_target = clean_target.replace("STORAGE WATER HEATER 2KW", "")
    clean_target = clean_target.replace("STORAGE WATER HEATER", "")
    clean_target = clean_target.replace("WH PLASTIC BODY WHITE GREY 2KW", "")
    clean_target = clean_target.replace("WH PLASTIC BODY 2KW", "")
    
    # Remove model family
    clean_target = clean_target.replace(model_family.upper(), "")
    # Remove model family fragments
    for frag in ["SILENCIO MINI", "ZOOMER PRIME", "ZOOMER DLX", "ELANZA NEO", "ELANZA PRIME", "ELEGANZ PEARL", "AFFECIENTE NEO", "AERO ULTRASPEED", "SILENCIO CRUISER PRIME", "SILENCIO CRUISER"]:
        clean_target = clean_target.replace(frag.upper(), "")
        
    # Remove words with word boundaries to avoid corruption of substrings (like WHITE, FANTASY, etc.)
    clean_target = re.sub(r'\b(CF|WF|PF|TF|EF|WH|HD|ES|HS|NS|BLDC|STAR|PRIME|DLX|PLUS|CLASSIC|II|NEO|FAN|C\s+FAN|DOMESTIC|EXHAUST|AXIAL|AXL|CABIN|STORAGE|HEATER|WATER|2KW|L|MM)\b', '', clean_target)
    
    # Remove size numbers and specs
    clean_target = re.sub(r'\b\d+(?:MM|C|L)?\b', '', clean_target)
    clean_target = re.sub(r'\b\d+\s*(?:INCH|MM|C)\b', '', clean_target)
    clean_target = re.sub(r'\d+["\w/.-]+', '', clean_target)
    
    # Clean up punctuation and double spaces
    clean_target = re.sub(r'[^A-Z0-9\s/+-]', '', clean_target)
    clean_target = clean_target.strip("/ ").strip()
    clean_target = re.sub(r'\s+', ' ', clean_target).strip()
    
    color = clean_target.title() if clean_target else "Standard"
    
    # 7. Formulate Proposed Group Name
    group_modifiers = []
    if re.search(r'\bES\b', name_upper):
        group_modifiers.append("ES")
    if re.search(r'\bBLDC\b', name_upper):
        group_modifiers.append("BLDC")
        
    modifier_str = " ".join(group_modifiers)
    model_name = model_family.title()
    if modifier_str:
        model_name = f"{model_name} {modifier_str}"
        
    if fan_type == "WH":
        proposed_group = f"{model_family} Water Heater"
    else:
        proposed_group = f"{model_name}"
        
    proposed_group = re.sub(r'\s+', ' ', proposed_group).strip().replace("Led", "LED")
    color = color.replace("Led", "LED")
    
    # 8. Formulate New Item Name (Variant Name)
    if fan_type == "WH":
        new_item_name = f"{size_prefix} {model_family} Water Heater {color}"
    else:
        new_item_name = f"{size_prefix} {fan_type} {model_family.title()} {color}{suffix}"
        
    new_item_name = re.sub(r'\s+', ' ', new_item_name).strip().replace("Led", "LED")
    
    return proposed_group, color, speed, size_attr, fan_type, new_item_name

def main():
    parser = argparse.ArgumentParser(description="Export Zoho fan items and prepare proposed variant groupings.")
    parser.add_argument("--execute", action="store_true", help="Unused for now (placeholder for step 3 confirmation).")
    args = parser.parse_args()

    try:
        tokens = fetch_access_tokens()
        client = get_inventory_client(token=tokens["inventory"], allow_books_token=True)
        
        purchase_acct_id = Config.FAN_PURCHASE_ACCOUNT_ID
        print(f"Fetching fan items from Zoho (Purchase Account: {purchase_acct_id})...")
        
        items = fetch_items_for_purchase_account(client, purchase_acct_id, status="active")
        items = [item for item in items if item.get("status") == "active"]
        all_count = len(items)
        items = [item for item in items if not item.get("group_id") and item.get("cf_deprecated") != "true" and item.get("cf_deprecated_unformatted") is not True]
        print(f"Fetched {all_count} active items from Zoho. Filtered to {len(items)} items (without group, non-deprecated).")
        
        if not items:
            print("No items found.")
            return

        os.makedirs("output/inventory", exist_ok=True)
        
        # --- STEP 1: Export Existing Zoho Fan Items to CSV ---
        existing_csv_path = "output/inventory/existing_zoho_fan_items.csv"
        df_existing = pd.DataFrame([{
            "item_id": item.get("item_id"),
            "name": item.get("name"),
            "sku": item.get("sku"),
            "unit": item.get("unit"),
            "purchase_rate": item.get("purchase_rate"),
            "rate": item.get("rate"),
            "status": item.get("status"),
            "item_group_id": item.get("item_group_id"),
            "item_group_name": item.get("item_group_name")
        } for item in items])
        
        df_existing.to_csv(existing_csv_path, index=False)
        print(f"✅ Step 1 complete: Exported existing items to {existing_csv_path}")

        # --- STEP 2: Generate Proposed Grouping CSV Files ---
        ceiling_csv_path = "output/inventory/proposed_ceiling_fan_groups.csv"
        exhaust_csv_path = "output/inventory/proposed_exhaust_fan_groups.csv"
        other_csv_path = "output/inventory/proposed_other_fan_groups.csv"
        
        ceiling_rows = []
        exhaust_rows = []
        other_rows = []
        
        for item in items:
            name = item.get("name", "")
            sku = item.get("sku", "")
            item_id = item.get("item_id")
            
            proposed_group_name, color, speed, size, fan_type, new_item_name = extract_attributes(name, sku)
            
            if fan_type == "CF":
                ceiling_rows.append({
                    "item_id": item_id,
                    "sku": sku,
                    "name": name,
                    "proposed_group_name": proposed_group_name,
                    "new_item_name": new_item_name,
                    "attribute_size": size,
                    "attribute_color": color
                })
            elif fan_type == "EF":
                exhaust_rows.append({
                    "item_id": item_id,
                    "sku": sku,
                    "name": name,
                    "proposed_group_name": proposed_group_name,
                    "new_item_name": new_item_name,
                    "attribute_size": size,
                    "attribute_color": color,
                    "attribute_speed": speed
                })
            else:
                other_rows.append({
                    "item_id": item_id,
                    "sku": sku,
                    "name": name,
                    "proposed_group_name": proposed_group_name,
                    "new_item_name": new_item_name,
                    "attribute_size": size,
                    "attribute_color": color,
                    "attribute_speed": speed,
                    "type": fan_type
                })
                
        # Save files sorted by SKU ascending
        df_ceiling = pd.DataFrame(ceiling_rows).sort_values("sku")
        df_ceiling.to_csv(ceiling_csv_path, index=False)
        
        df_exhaust = pd.DataFrame(exhaust_rows).sort_values("sku")
        df_exhaust.to_csv(exhaust_csv_path, index=False)
        
        df_other = pd.DataFrame(other_rows).sort_values("sku")
        df_other.to_csv(other_csv_path, index=False)
        
        print(f"✅ Step 2 complete: Generated separate groupings mapping CSV files:")
        print(f"  - Ceiling Fans (Count: {len(df_ceiling)}): {ceiling_csv_path}")
        print(f"  - Exhaust Fans (Count: {len(df_exhaust)}): {exhaust_csv_path}")
        print(f"  - Other Fan Types/Items (Count: {len(df_other)}): {other_csv_path}")
        
        # Display sample ceiling output
        print("\nTop 5 Proposed Ceiling Fan Groups:")
        if not df_ceiling.empty:
            print(df_ceiling["proposed_group_name"].value_counts().head(5).to_string())
        
        # Display sample exhaust output
        print("\nTop 5 Proposed Exhaust Fan Groups:")
        if not df_exhaust.empty:
            print(df_exhaust["proposed_group_name"].value_counts().head(5).to_string())
        
        print("\n=== STEP 3: Awaiting user confirmation ===")
        print("Please review the generated CSV files. If the proposed group names and attributes look correct, we can proceed.")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
