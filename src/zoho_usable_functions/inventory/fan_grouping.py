"""Domain logic for FAN item categorization, sweep size conversions, and group proposals."""

from __future__ import annotations

from typing import Any

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
    225: 9,
}
INCH_TO_MM = {v: k for k, v in MM_TO_INCH.items()}

# Existing group mappings in Zoho Books
EXISTING_FAN_GROUPS = {
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


def classify_item_type(item: dict[str, Any]) -> str:
    """Classify item product type based on SKU prefixes, item names, and Zoho categories."""
    name = (item.get("name") or item.get("item_name") or "").lower()
    sku = (item.get("sku") or item.get("item_sku") or "").upper()
    cat = item.get("category_name") or ""

    if "rate difference" in name:
        return "Adjustment/Service"

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


def propose_fan_group(name: str, sku: str, prod_type: str) -> tuple[str, str, str]:
    """Suggest Group Name, Group ID, and action for a FAN item based on name, SKU, and product type."""
    n_lower = name.lower()
    s_upper = sku.upper()

    if prod_type == "Exhaust Fan":
        if "freshner neo" in n_lower:
            return "Freshner Neo", EXISTING_FAN_GROUPS["Freshner Neo"], "Assign to Existing Group"
        elif "freshobreeze" in n_lower:
            return "Freshobreeze", EXISTING_FAN_GROUPS["Freshobreeze"], "Assign to Existing Group"
        elif "freshner metal" in n_lower or "freshner reversible metal" in n_lower:
            return "Freshner Metal", EXISTING_FAN_GROUPS["Freshner Metal"], "Assign to Existing Group"
        elif "airofresh" in n_lower or s_upper.startswith("FEXDOA"):
            return "Airofresh", EXISTING_FAN_GROUPS["Airofresh"], "Assign to Existing Group"
        elif "hd ef" in n_lower or "heavy duty" in n_lower or "superb" in n_lower or s_upper.startswith("FEXINH"):
            return "Heavy Duty Exhaust", EXISTING_FAN_GROUPS["Heavy Duty Exhaust"], "Assign to Existing Group"
        elif "freshner" in n_lower:
            return "Freshner Metal", EXISTING_FAN_GROUPS["Freshner Metal"], "Assign to Existing Group"

    elif prod_type == "Pedestal Fan":
        if "farrata" in n_lower:
            return "PF Faratta", EXISTING_FAN_GROUPS["PF Faratta"], "Assign to Existing Group"
        elif "hs" in n_lower or s_upper.startswith("FPEH"):
            return "PF HS", EXISTING_FAN_GROUPS["PF HS"], "Assign to Existing Group"
        elif "ns" in n_lower or s_upper.startswith("FPEN"):
            return "PF NS", EXISTING_FAN_GROUPS["PF NS"], "Assign to Existing Group"
        else:
            return "PF HS", EXISTING_FAN_GROUPS["PF HS"], "Assign to Existing Group"

    elif prod_type == "Table Fan":
        if "hs" in n_lower or s_upper.startswith("FTAH"):
            return "TF HS", EXISTING_FAN_GROUPS["TF HS"], "Assign to Existing Group"
        elif "ns" in n_lower or s_upper.startswith("FTAN"):
            return "TF NS", EXISTING_FAN_GROUPS["TF NS"], "Assign to Existing Group"
        else:
            return "TF HS", EXISTING_FAN_GROUPS["TF HS"], "Assign to Existing Group"

    elif prod_type == "Wall Fan":
        if "hs" in n_lower or s_upper.startswith("FWAH"):
            return "WF HS", EXISTING_FAN_GROUPS["WF HS"], "Assign to Existing Group"
        elif "ns" in n_lower or s_upper.startswith("FWAN"):
            return "WF NS", EXISTING_FAN_GROUPS["WF NS"], "Assign to Existing Group"
        else:
            return "WF HS", EXISTING_FAN_GROUPS["WF HS"], "Assign to Existing Group"

    elif prod_type == "Air Circulator":
        if "acp" in n_lower or s_upper.startswith("FACACP"):
            return "ACP", EXISTING_FAN_GROUPS["ACP"], "Assign to Existing Group"
        elif "acw" in n_lower or s_upper.startswith("FACACW"):
            return "ACW", EXISTING_FAN_GROUPS["ACW"], "Assign to Existing Group"

    return "", "", "Review Required"
