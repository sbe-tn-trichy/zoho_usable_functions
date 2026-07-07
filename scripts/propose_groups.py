import csv
import os
import re
from typing import Dict, Any, List, Tuple

# Mapping of all existing item group names and their Zoho Books Group IDs
EXISTING_GROUPS = {
    "PF NS": "1094368000029003437",
    "PF HS": "1094368000029148390",
    "PF Faratta": "1094368000029148494",
    "TF NS": "1094368000029148605",
    "TF HS": "1094368000029148694",
    "WF NS": "1094368000029148653",
    "WF HS": "1094368000029194379",
    "Heavy Duty Exhaust": "1094368000029003468",
    "Freshner Metal": "1094368000029003517",
    "Freshner Neo": "1094368000029003589",
    "Freshobreeze": "1094368000029148777",
    "Airofresh": "1094368000029148800",
    "ACP": "1094368000029148908",
    "ACW": "1094368000029148942",
    "Silencio Mini": "1094368000047435041",
    "Silencio Mini DLX": "1094368000047435191",
    "Silencio Mini LED": "1094368000047380366",
    "Silencio Cruiser": "1094368000029275076",
    "Elanza Neo": "1094368000047199580",
    "Elanza Prime": "1094368000005520157",
    "Affeciente Neo": "1094368000029275271",
    "Zoomer HS": "1094368000047216930",
    "Zoomer Dlx": "1094368000047281051",
    "Zoomer Prime": "1094368000044215508",
    "Zoomer Prime ES": "1094368000056484626",
}

def propose_group(name: str, sku: str, prod_type: str) -> Tuple[str, str, str]:
    """
    Suggests a Group Name, Group ID, and action based on item names, SKU, and type.
    """
    n_lower = name.lower()
    s_upper = sku.upper()
    
    # 1. Exhaust Fans
    if prod_type == "Exhaust Fan":
        if "freshner neo" in n_lower:
            return "Freshner Neo", EXISTING_GROUPS["Freshner Neo"], "Assign to Existing Group"
        elif "freshobreeze" in n_lower:
            return "Freshobreeze", EXISTING_GROUPS["Freshobreeze"], "Assign to Existing Group"
        elif "freshner metal" in n_lower or "freshner reversible metal" in n_lower:
            return "Freshner Metal", EXISTING_GROUPS["Freshner Metal"], "Assign to Existing Group"
        elif "airofresh" in n_lower or s_upper.startswith("FEXDOA"):
            return "Airofresh", EXISTING_GROUPS["Airofresh"], "Assign to Existing Group"
        elif "hd ef" in n_lower or "heavy duty" in n_lower or "superb" in n_lower or s_upper.startswith("FEXINH"):
            return "Heavy Duty Exhaust", EXISTING_GROUPS["Heavy Duty Exhaust"], "Assign to Existing Group"
        elif "freshner" in n_lower:
            return "Freshner Metal", EXISTING_GROUPS["Freshner Metal"], "Assign to Existing Group"
            
    # 2. Pedestal Fans
    elif prod_type == "Pedestal Fan":
        if "farrata" in n_lower:
            return "PF Faratta", EXISTING_GROUPS["PF Faratta"], "Assign to Existing Group"
        elif "hs" in n_lower or s_upper.startswith("FPEH"):
            return "PF HS", EXISTING_GROUPS["PF HS"], "Assign to Existing Group"
        elif "ns" in n_lower or s_upper.startswith("FPEN"):
            return "PF NS", EXISTING_GROUPS["PF NS"], "Assign to Existing Group"
        else:
            return "PF HS", EXISTING_GROUPS["PF HS"], "Assign to Existing Group"
            
    # 3. Table Fans
    elif prod_type == "Table Fan":
        if "hs" in n_lower or s_upper.startswith("FTAH"):
            return "TF HS", EXISTING_GROUPS["TF HS"], "Assign to Existing Group"
        elif "ns" in n_lower or s_upper.startswith("FTAN"):
            return "TF NS", EXISTING_GROUPS["TF NS"], "Assign to Existing Group"
        else:
            return "TF HS", EXISTING_GROUPS["TF HS"], "Assign to Existing Group"
            
    # 4. Wall Fans
    elif prod_type == "Wall Fan":
        if "hs" in n_lower or s_upper.startswith("FWAH"):
            return "WF HS", EXISTING_GROUPS["WF HS"], "Assign to Existing Group"
        elif "ns" in n_lower or s_upper.startswith("FWAN"):
            return "WF NS", EXISTING_GROUPS["WF NS"], "Assign to Existing Group"
        else:
            return "WF HS", EXISTING_GROUPS["WF HS"], "Assign to Existing Group"
            
    # 5. Air Circulator
    elif prod_type == "Air Circulator":
        if "acw" in n_lower or s_upper.startswith("FACW"):
            return "ACW", EXISTING_GROUPS["ACW"], "Assign to Existing Group"
        elif "acp" in n_lower or s_upper.startswith("FACP"):
            return "ACP", EXISTING_GROUPS["ACP"], "Assign to Existing Group"
            
    # 6. Ceiling Fans
    elif prod_type == "Ceiling Fan":
        if "silencio mini dlx" in n_lower:
            return "Silencio Mini DLX", EXISTING_GROUPS["Silencio Mini DLX"], "Assign to Existing Group"
        elif "silencio mini led" in n_lower:
            return "Silencio Mini LED", EXISTING_GROUPS["Silencio Mini LED"], "Assign to Existing Group"
        elif "silencio mini" in n_lower:
            return "Silencio Mini", EXISTING_GROUPS["Silencio Mini"], "Assign to Existing Group"
        elif "silencio cruiser" in n_lower:
            return "Silencio Cruiser", EXISTING_GROUPS["Silencio Cruiser"], "Assign to Existing Group"
        elif "elanza neo" in n_lower:
            return "Elanza Neo", EXISTING_GROUPS["Elanza Neo"], "Assign to Existing Group"
        elif "elanza prime" in n_lower:
            return "Elanza Prime", EXISTING_GROUPS["Elanza Prime"], "Assign to Existing Group"
        elif "affeciente neo" in n_lower:
            return "Affeciente Neo", EXISTING_GROUPS["Affeciente Neo"], "Assign to Existing Group"
        elif "zoomer dlx" in n_lower:
            return "Zoomer Dlx", EXISTING_GROUPS["Zoomer Dlx"], "Assign to Existing Group"
        elif "zoomer prime es" in n_lower or (s_upper.startswith("FCEECS") and "zoomer prime" in n_lower and "es" in n_lower):
            return "Zoomer Prime ES", EXISTING_GROUPS["Zoomer Prime ES"], "Assign to Existing Group"
        elif "zoomer prime" in n_lower:
            return "Zoomer Prime", EXISTING_GROUPS["Zoomer Prime"], "Assign to Existing Group"
        elif "zoomer" in n_lower:
            return "Zoomer HS", EXISTING_GROUPS["Zoomer HS"], "Assign to Existing Group"
            
        # Models without existing group - suggest creating a new group
        elif "aero ultraspeed" in n_lower:
            return "Aero Ultraspeed", "", "Create New Group"
        elif "aerofame" in n_lower:
            return "Aerofame", "", "Create New Group"
        elif "aerorush" in n_lower:
            return "Aerorush", "", "Create New Group"
        elif "airika" in n_lower:
            return "Airika R28", "", "Create New Group"
        elif "aria" in n_lower:
            return "Aria28", "", "Create New Group"
        elif "juno" in n_lower:
            return "Juno", "", "Create New Group"
        elif "eteri" in n_lower:
            return "Eteri", "", "Create New Group"
            
    # 7. Water Heaters
    elif prod_type == "Water Heater":
        if "superia" in n_lower:
            return "Superia Heaters", "", "Create New Group"
        elif "intenso" in n_lower:
            return "Intenso Heaters", "", "Create New Group"
            
    return "Other / Miscellaneous", "", "Create New Group"

def append_suffix_from_name(group_name: str, name: str) -> str:
    """
    Appends BLDC, HS, or ES suffix to the group name if present in item name
    and not already part of the group name.
    """
    n_upper = name.upper()
    g_upper = group_name.upper()
    
    # 1. Handle BLDC suffix
    if "BLDC" in n_upper and "BLDC" not in g_upper:
        group_name = f"{group_name} BLDC"
        g_upper = group_name.upper()
        
    # 2. Handle HS/ES/NS suffix
    if not g_upper.endswith((" HS", " ES", " NS")):
        if re.search(r'\bHS\b', name):
            group_name = f"{group_name} HS"
        elif re.search(r'\bES\b', name):
            group_name = f"{group_name} ES"
            
    return group_name

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_csv = os.path.join(repo_root, "output", "fan_purchase_items_active_no_group.csv")
    
    if not os.path.exists(input_csv):
        # try parent folder
        input_csv = os.path.join(os.path.dirname(repo_root), "fan_purchase_items_active_no_group.csv")
        
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found. Run export_fan_purchase_items.py first.")
        return
        
    print(f"Loading group-less active items from: {input_csv}")
    with open(input_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        items = list(reader)
        
    print(f"Loaded {len(items)} items. Matching groups...")
    
    proposed_assignments = []
    actions_count = {"Assign to Existing Group": 0, "Create New Group": 0}
    groups_proposed = {}
    
    for item in items:
        name = item.get("Name", "")
        sku = item.get("SKU", "")
        prod_type = item.get("Inferred Type", "")
        
        proposed_name, proposed_id, action = propose_group(name, sku, prod_type)
        
        # Apply speed/efficiency suffixes (HS/ES) to the proposed group name
        proposed_name = append_suffix_from_name(proposed_name, name)
        
        # Recalculate Proposed Action based on the final group name
        if proposed_name in EXISTING_GROUPS:
            action = "Assign to Existing Group"
        else:
            action = "Create New Group"
            
        actions_count[action] = actions_count.get(action, 0) + 1
        groups_proposed[proposed_name] = groups_proposed.get(proposed_name, 0) + 1
        
        # Resolve Attribute 1 (size)
        attr1_name = "size"
        attr1_value = ""
        sweep_mm = item.get("Sweep (mm)", "")
        if sweep_mm:
            attr1_value = f"{sweep_mm}mm"
        else:
            # check for water heater capacity (e.g. "10L", "3L") from Name
            heater_match = re.search(r'\b(\d+L)\b', name, re.IGNORECASE)
            if heater_match:
                attr1_value = heater_match.group(1).upper()
                
        # Resolve Attribute 2 (colour)
        attr2_name = "colour"
        attr2_value = ""
        color_val = item.get("Color", "")
        if color_val and color_val.lower() not in ["", "unspecified", "nil", "na"]:
            attr2_value = color_val
        else:
            attr2_value = "N/A"

        proposed_assignments.append({
            "Item ID": item.get("Item ID", ""),
            "Name": name,
            "SKU": sku,
            "Inferred Type": prod_type,
            "Inferred Tier": item.get("Inferred Tier", ""),
            "Sweep (mm)": sweep_mm,
            "Sweep (inches)": item.get("Sweep (inches)", ""),
            "Model/Series": item.get("Model/Series", ""),
            "Color": color_val,
            "Current Group Name": "",
            "Current Group ID": "",
            "Proposed Group Name": proposed_name,
            "Proposed Action": action,
            "Attribute 1 Name": attr1_name,
            "Attribute 1 Value": attr1_value,
            "Attribute 2 Name": attr2_name,
            "Attribute 2 Value": attr2_value
        })
        
    # Sort alphabetically by Proposed Group Name
    proposed_assignments.sort(key=lambda x: x["Proposed Group Name"].lower())
        
    # Headers for proposed output
    headers = [
        "Item ID", "Name", "SKU", "Inferred Type", "Inferred Tier", 
        "Sweep (mm)", "Sweep (inches)", "Model/Series", "Color", 
        "Current Group Name", "Current Group ID", "Proposed Group Name", 
        "Proposed Action", "Attribute 1 Name", "Attribute 1 Value", 
        "Attribute 2 Name", "Attribute 2 Value"
    ]
    
    # Save files
    local_output_dir = os.path.join(repo_root, "output")
    local_out_csv = os.path.join(local_output_dir, "proposed_group_assignments.csv")
    workspace_out_csv = os.path.join(os.path.dirname(repo_root), "proposed_group_assignments.csv")
    
    try:
        with open(local_out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(proposed_assignments)
        print(f"Saved local proposal CSV to: {os.path.abspath(local_out_csv)}")
    except Exception as e:
        print(f"Error saving local proposal CSV: {e}")
        
    try:
        with open(workspace_out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(proposed_assignments)
        print(f"Saved workspace proposal CSV to: {workspace_out_csv}")
    except Exception as e:
        print(f"Error saving workspace proposal CSV: {e}")
        
    # Print statistics
    print("\n" + "="*50)
    print("PROPOSED GROUP ASSIGNMENTS STATS")
    print("="*50)
    print("\nBY PROPOSED ACTION:")
    for a, count in actions_count.items():
        print(f"  - {a:25}: {count}")
        
    print("\nBY PROPOSED GROUP NAME:")
    for g, count in sorted(groups_proposed.items(), key=lambda x: x[1], reverse=True):
        status = "Existing" if g in EXISTING_GROUPS else "NEW"
        print(f"  - {g:25} ({status:8}): {count}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
