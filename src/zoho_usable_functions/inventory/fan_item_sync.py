"""FAN-specific adapter for the generic Zoho Inventory item sync workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd
from zoho.inventory import ZohoInventoryAPI

from ..core.auth import get_inventory_client
from .constants import (
    DEFAULT_CREATE_XLSX,
    DEFAULT_EXISTING_SNAPSHOT,
    DEFAULT_FAN_ACCOUNTS,
    DEFAULT_FAN_FILE,
    DEFAULT_OUTPUT_DIR,
    FAN_FILENAME_PREFIX,
    FAN_STOCK_REPORT_FIELDS,
    GST_18_TAX_PREFERENCES,
)
from .fan_stock_report import read_fan_stock_report
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


def load_fan_candidates(path: str | Path = DEFAULT_FAN_FILE, accounts: Optional[dict[str, str]] = None) -> pd.DataFrame:
    """Load valid FAN stock rows and map them to the item-master columns."""
    path = Path(path)
    accounts = accounts or DEFAULT_FAN_ACCOUNTS
    main = read_fan_stock_report(path, FAN_STOCK_REPORT_FIELDS)
    main = main[main["sku"].notna()].copy()
    main = main[main["status"].str.upper() == "LIVE"].copy()
    main = main[main["category"].str.upper() != "CEILING-DUM"].copy()
    main = main[main["channel"].str.upper().isin({"TRADE", "ECOM+TRADE", "B2B+TRADE"})].copy()

    out = pd.DataFrame(
        {
            "SKU": main["sku"],
            "Item Name": main["description"],
            "Status": main["status"].replace({"LIVE": "Live"}),
            "Type": "Inventory",
            "Usage unit": "NOS",
            "account_id": accounts["account_id"],
            "purchase_account_id": accounts["purchase_account_id"],
            "inventory_account_id": accounts["inventory_account_id"],
            "Product Category": main["category"],
            "Product Type": main["product_type"],
            "Brand": "Polycab",
            "Manufacturer": "Polycab",
            "Sales Description": main["description"],
            "Purchase Description": main["description"],
            "Source": f"FAN BU Stock GIT {path.stem[-10:]}",
            "Opening Stock": 0,
            "Opening Stock Value": 0,
            "FAN Category": main["category"],
            "FAN Model Group": main["model_group"],
            "FAN Channel": main["channel"],
            "FAN Status Raw": main["status"],
            "FAN Grand Stock": main["grand_stock"],
            "FAN Grand GIT": main["grand_git"],
            "FAN Total Stock + GIT": main["total_stock_and_git"],
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
