"""FAN-specific adapter for the generic Zoho Inventory item sync workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd
from zoho.inventory import ZohoInventoryAPI

from ..core.auth import get_inventory_client
from ..core.config import Config
from .item_sync import (
    build_inventory_item_payload,
    compare_items_with_inventory,
    create_inventory_items_from_sheet as create_items_from_sheet,
    fetch_inventory_items,
    items_to_frame,
    normalize_sku,
    prepare_inventory_items_from_sheet,
    write_item_diff_outputs,
)


DEFAULT_FAN_FILE = Path(Config.FAN_STOCK_FILE)
DEFAULT_OUTPUT_DIR = Path(Config.FAN_OUTPUT_DIR)
FAN_FILENAME_PREFIX = "zoho_inventory_fan_items"
DEFAULT_EXISTING_SNAPSHOT = DEFAULT_OUTPUT_DIR / "zoho_inventory_existing_items_snapshot.csv"
DEFAULT_CREATE_XLSX = DEFAULT_OUTPUT_DIR / f"{FAN_FILENAME_PREFIX}_missing.xlsx"
DEFAULT_FAN_ACCOUNTS = {
    "account_id": Config.FAN_SALES_ACCOUNT_ID,
    "purchase_account_id": Config.FAN_PURCHASE_ACCOUNT_ID,
    "inventory_account_id": Config.FAN_INVENTORY_ACCOUNT_ID,
}
GST_18_TAX_PREFERENCES = [
    {
        "tax_specification": "intra",
        "tax_name": "GST18",
        "tax_percentage": 18,
        "tax_id": Config.ZOHO_GST18_TAX_ID,
    },
    {
        "tax_specification": "inter",
        "tax_name": "IGST18",
        "tax_percentage": 18,
        "tax_id": Config.ZOHO_IGST18_TAX_ID,
    },
]


def load_fan_candidates(path: str | Path = DEFAULT_FAN_FILE, accounts: Optional[dict[str, str]] = None) -> pd.DataFrame:
    """Load valid FAN stock rows and map them to the item-master columns."""
    path = Path(path)
    accounts = accounts or DEFAULT_FAN_ACCOUNTS
    main = pd.read_excel(path, sheet_name="MAIN", header=3)
    main = main[main["SKU"].notna()].copy()

    for col in ["CATEGORY", "MODEL", "SKU", "Description", "Model", "Channel", "Status"]:
        if col in main.columns:
            main[col] = main[col].astype(str).str.strip()
    main = main[main["Status"].str.upper() == "LIVE"].copy()
    main = main[main["CATEGORY"].str.upper() != "CEILING-DUM"].copy()
    main = main[main["Channel"].str.upper().isin({"TRADE", "ECOM+TRADE", "B2B+TRADE"})].copy()

    for col in main.columns[7:]:
        main[col] = pd.to_numeric(main[col], errors="coerce").fillna(0)

    stock_col = main.columns[79]
    git_col = main.columns[80]

    out = pd.DataFrame(
        {
            "SKU": main["SKU"],
            "Item Name": main["Description"],
            "Status": main["Status"].replace({"LIVE": "Live"}),
            "Type": "Inventory",
            "Usage unit": "NOS",
            "account_id": accounts["account_id"],
            "purchase_account_id": accounts["purchase_account_id"],
            "inventory_account_id": accounts["inventory_account_id"],
            "Product Category": main["CATEGORY"],
            "Product Type": main["Model"],
            "Brand": "Polycab",
            "Manufacturer": "Polycab",
            "Sales Description": main["Description"],
            "Purchase Description": main["Description"],
            "Source": f"FAN BU Stock GIT {path.stem[-10:]}",
            "Opening Stock": 0,
            "Opening Stock Value": 0,
            "FAN Category": main["CATEGORY"],
            "FAN Model Group": main["MODEL"],
            "FAN Channel": main["Channel"],
            "FAN Status Raw": main["Status"],
            "FAN Grand Stock": main[stock_col].astype(int),
            "FAN Grand GIT": main[git_col].astype(int),
            "FAN Total Stock + GIT": main["Total stock +GIT"].astype(int),
        }
    )
    out["SKU_KEY"] = out["SKU"].map(normalize_sku)
    out = out[out["SKU_KEY"] != ""]
    return out.drop_duplicates(subset=["SKU_KEY"], keep="first").sort_values("SKU")


def fetch_all_inventory_items(
    client: ZohoInventoryAPI,
    purchase_account_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Backward-compatible alias for the generic Inventory fetch helper."""
    return fetch_inventory_items(client, purchase_account_id, max_pages, verbose)


def inventory_items_to_frame(items: list[dict[str, Any]]) -> pd.DataFrame:
    existing = items_to_frame(items)
    return existing.rename(columns={"MATCH_KEY": "SKU_KEY"}) if "SKU_KEY" not in existing.columns else existing


def write_fan_item_outputs(
    candidates: pd.DataFrame,
    missing: pd.DataFrame,
    existing: pd.DataFrame,
    changed: Optional[pd.DataFrame] = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    changed = changed if changed is not None else pd.DataFrame()
    duplicates = candidates.iloc[0:0].copy()
    diff = {
        "target": candidates,
        "existing": existing,
        "missing": missing,
        "changed": changed,
        "duplicates": duplicates,
        "summary": {
            "target_rows": len(candidates),
            "existing_items": existing["SKU_KEY"].nunique() if "SKU_KEY" in existing else 0,
            "missing": len(missing),
            "changed": len(changed),
            "unchanged": max(len(candidates) - len(missing) - len(changed), 0),
            "duplicates": 0,
        },
    }
    return write_item_diff_outputs(
        diff,
        output_dir,
        filename_prefix=FAN_FILENAME_PREFIX,
        report_label="FAN candidate",
    )


def compare_fan_items_with_inventory(
    fan_file: str | Path = DEFAULT_FAN_FILE,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    existing_items_file: Optional[str | Path] = None,
    client: Optional[ZohoInventoryAPI] = None,
    accounts: Optional[dict[str, str]] = None,
    max_pages: Optional[int] = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Compare FAN stock SKUs with Zoho Inventory and write missing-item outputs."""
    accounts = accounts or DEFAULT_FAN_ACCOUNTS
    candidates = load_fan_candidates(fan_file, accounts)
    results = compare_items_with_inventory(
        candidates,
        output_dir,
        client=client,
        client_factory=get_inventory_client,
        existing_items_file=existing_items_file or DEFAULT_EXISTING_SNAPSHOT,
        purchase_account_id=accounts["purchase_account_id"],
        max_pages=max_pages,
        filename_prefix=FAN_FILENAME_PREFIX,
        report_label="FAN candidate",
        verbose=verbose,
    )
    generic_summary = results["summary"]
    results["summary"] = {
        "fan_candidate_skus": generic_summary["target_rows"],
        "zoho_inventory_item_skus": generic_summary["existing_items"],
        "missing_fan_skus": generic_summary["missing"],
        "changed_fan_skus": generic_summary["changed"],
        "duplicate_fan_skus": generic_summary["duplicates"],
    }
    return results


def build_create_payload(row: pd.Series) -> tuple[dict[str, Any], list[str]]:
    return build_inventory_item_payload(row, defaults=DEFAULT_FAN_ACCOUNTS, tax_preferences=GST_18_TAX_PREFERENCES)


def prepare_inventory_item_payloads(
    create_xlsx: str | Path = DEFAULT_CREATE_XLSX,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Read the edited Missing_Items sheet and write payload/validation previews."""
    return prepare_inventory_items_from_sheet(
        create_xlsx,
        output_dir,
        payload_builder=build_create_payload,
        filename_prefix="zoho_inventory_create",
    )


def create_inventory_items_from_sheet(
    create_xlsx: str | Path = DEFAULT_CREATE_XLSX,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    client: Optional[ZohoInventoryAPI] = None,
    abort_on_blocking: bool = True,
) -> dict[str, Any]:
    """Prepare payloads and create items in Zoho Inventory."""
    return create_items_from_sheet(
        create_xlsx,
        output_dir,
        client=client,
        client_factory=get_inventory_client,
        payload_builder=build_create_payload,
        filename_prefix="zoho_inventory_create",
        abort_on_blocking=abort_on_blocking,
    )
