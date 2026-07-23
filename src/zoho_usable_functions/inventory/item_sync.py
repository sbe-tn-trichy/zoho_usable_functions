"""Generic Zoho Inventory item sync helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd


DEFAULT_COMPARE_FIELDS = [
    ("Item Name", "name", "name"),
    ("Usage unit", "unit", "unit"),
    ("rate", "rate", "rate"),
    ("purchase_rate", "purchase_rate", "purchase_rate"),
    ("account_id", "account_id", "account_id"),
    ("purchase_account_id", "purchase_account_id", "purchase_account_id"),
    ("inventory_account_id", "inventory_account_id", "inventory_account_id"),
    ("HSN/SAC", "hsn_or_sac", "hsn_or_sac"),
]


def normalize_sku(value: Any) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in str(value).strip().upper() if ch.isalnum())


def first_present(row: pd.Series, names: list[str], default: Any = None) -> Any:
    for name in names:
        if name in row.index and pd.notna(row[name]) and str(row[name]).strip() != "":
            return row[name]
    return default


def number_or_zero(value: Any) -> tuple[float, bool]:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return 0.0, True
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return 0.0, True
    return float(number), False


def extract_item_sku(item: dict[str, Any]) -> str:
    for key in ("sku", "SKU", "item_sku", "item_code", "code"):
        sku = normalize_sku(item.get(key))
        if sku:
            return sku
    return ""


def fetch_items_for_purchase_account(client: Any, purchase_account_id: Optional[str], status: str = "all") -> list[dict[str, Any]]:
    """Fetch Zoho Inventory items through the SDK resource."""
    return client.items.list_by_purchase_account(purchase_account_id, status=status)


def fetch_inventory_items(
    client: Any,
    purchase_account_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Fetch Inventory items, optionally limiting explicit 200-item pages.

    With no page limit this delegates to the SDK's pagination-aware helper.
    ``max_pages`` is useful for previews and test runs.
    """
    if max_pages is None:
        if verbose:
            print("Fetching Zoho Inventory items through SDK list_all...", flush=True)
        return fetch_items_for_purchase_account(client, purchase_account_id)

    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        if verbose:
            print(f"Fetching Zoho Inventory items page {page}...", flush=True)
        params: dict[str, Any] = {"page": page, "per_page": 200}
        if purchase_account_id:
            params["purchase_account_id"] = purchase_account_id
        response = client.items.list(params=params)
        page_items = response.get("items", [])
        items.extend(page_items)
        if verbose:
            print(f"  fetched {len(page_items)} items; total {len(items)}", flush=True)
        if not response.get("page_context", {}).get("has_more_page", False):
            break
    return items


def fetch_items_by_status(client: Any, status: str = "active") -> list[dict[str, Any]]:
    """Fetch Zoho Inventory items filtered by active/inactive status."""
    return client.items.list_by_status(status=status)


def find_active_items_with_name_containing(
    client: Any,
    needle: str = "_old",
    items: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Return active Zoho Inventory items whose names contain the supplied text."""
    source_items = items if items is not None else fetch_items_by_status(client, status="active")
    needle_lower = needle.lower()
    return [
        item
        for item in source_items
        if item.get("status") == "active" and needle_lower in str(item.get("name") or "").lower()
    ]


def mark_inventory_items_inactive(
    client: Any,
    item_ids: list[str],
    batch_size: int = 200,
) -> list[dict[str, Any]]:
    """Mark Zoho Inventory items inactive using the bulk inactive endpoint."""
    sdk_results = client.items.mark_inactive_bulk(item_ids, batch_size=batch_size)
    return [
        {
            "item_ids": result["item_ids"],
            "code": result["response"].get("code") if isinstance(result["response"], dict) else None,
            "message": result["response"].get("message", "") if isinstance(result["response"], dict) else str(result["response"]),
            "response": result["response"],
        }
        for result in sdk_results
    ]


def items_to_frame(items: list[dict[str, Any]], match_key: str = "sku") -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append(
            {
                "item_id": item.get("item_id") or item.get("id"),
                "name": item.get("name"),
                "sku": extract_item_sku(item),
                "unit": item.get("unit"),
                "rate": item.get("rate"),
                "purchase_rate": item.get("purchase_rate"),
                "account_id": item.get("account_id"),
                "purchase_account_id": item.get("purchase_account_id"),
                "inventory_account_id": item.get("inventory_account_id"),
                "hsn_or_sac": item.get("hsn_or_sac"),
                "status": item.get("status"),
                "raw_item_type": item.get("item_type"),
                "product_type": item.get("product_type"),
            }
        )
    existing = pd.DataFrame(rows)
    if existing.empty:
        existing = pd.DataFrame(
            columns=[
                "item_id",
                "name",
                "sku",
                "unit",
                "rate",
                "purchase_rate",
                "account_id",
                "purchase_account_id",
                "inventory_account_id",
                "hsn_or_sac",
                "status",
                "raw_item_type",
                "product_type",
            ]
        )
    if match_key not in existing.columns:
        existing[match_key] = ""
    existing["MATCH_KEY"] = existing[match_key].map(normalize_sku)
    if match_key == "sku":
        existing["SKU_KEY"] = existing["MATCH_KEY"]
    return existing


def _target_match_value(row: pd.Series, match_key: str) -> Any:
    if match_key in row.index:
        return row[match_key]
    if match_key.lower() == "sku":
        return first_present(row, ["SKU", "sku"], "")
    return ""


def _values_differ(left: Any, right: Any) -> bool:
    if pd.isna(left) and pd.isna(right):
        return False
    if pd.isna(left) or pd.isna(right):
        return str(left if not pd.isna(left) else "").strip() != str(right if not pd.isna(right) else "").strip()
    left_number = pd.to_numeric(left, errors="coerce")
    right_number = pd.to_numeric(right, errors="coerce")
    if not pd.isna(left_number) and not pd.isna(right_number):
        return float(left_number) != float(right_number)
    return str(left).strip() != str(right).strip()


def _normalize_compare_fields(compare_fields: Optional[list[Any]]) -> list[tuple[str, str, str]]:
    fields = compare_fields or DEFAULT_COMPARE_FIELDS
    normalized = []
    for field in fields:
        if isinstance(field, tuple):
            if len(field) == 2:
                normalized.append((field[0], field[1], field[1]))
            elif len(field) == 3:
                normalized.append(field)
            else:
                raise ValueError("compare field tuples must have 2 or 3 values")
        else:
            normalized.append((str(field), str(field), str(field)))
    return normalized


def find_item_diff(
    target_rows: pd.DataFrame,
    existing_items: pd.DataFrame,
    match_key: str = "sku",
    compare_fields: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Classify target rows as missing, changed, unchanged, or duplicate."""
    target = target_rows.copy()
    if "MATCH_KEY" not in target.columns:
        target["MATCH_KEY"] = target.apply(lambda row: normalize_sku(_target_match_value(row, match_key)), axis=1)
    if "SKU_KEY" not in target.columns and match_key.lower() == "sku":
        target["SKU_KEY"] = target["MATCH_KEY"]

    existing = existing_items.copy()
    if "MATCH_KEY" not in existing.columns:
        if match_key in existing.columns:
            existing["MATCH_KEY"] = existing[match_key].map(normalize_sku)
        elif match_key.lower() == "sku" and "sku" in existing.columns:
            existing["MATCH_KEY"] = existing["sku"].map(normalize_sku)
        else:
            existing["MATCH_KEY"] = ""

    duplicate_mask = target["MATCH_KEY"].ne("") & target["MATCH_KEY"].duplicated(keep=False)
    duplicates = target[duplicate_mask].copy()
    deduped = target[~duplicate_mask].copy()

    existing_index = existing[existing["MATCH_KEY"].ne("")].drop_duplicates("MATCH_KEY").set_index("MATCH_KEY")
    missing = deduped[~deduped["MATCH_KEY"].isin(existing_index.index)].copy()

    changed_records: list[dict[str, Any]] = []
    unchanged_indexes: list[Any] = []
    fields = _normalize_compare_fields(compare_fields)
    for index, row in deduped[deduped["MATCH_KEY"].isin(existing_index.index)].iterrows():
        existing_row = existing_index.loc[row["MATCH_KEY"]]
        differences = []
        for target_col, existing_col, label in fields:
            if target_col not in row.index or existing_col not in existing_row.index:
                continue
            target_value = row[target_col]
            existing_value = existing_row[existing_col]
            if _values_differ(target_value, existing_value):
                differences.append(
                    {
                        "field": label,
                        "target_value": target_value,
                        "existing_value": existing_value,
                    }
                )
        if differences:
            changed_records.append(
                {
                    "MATCH_KEY": row["MATCH_KEY"],
                    "SKU": first_present(row, ["SKU", "sku"], ""),
                    "item_id": existing_row.get("item_id", ""),
                    "name": first_present(row, ["Item Name", "Name", "name"], ""),
                    "differences": differences,
                    "differences_text": "; ".join(
                        f"{diff['field']}: target={diff['target_value']} existing={diff['existing_value']}"
                        for diff in differences
                    ),
                }
            )
        else:
            unchanged_indexes.append(index)

    changed = pd.DataFrame(changed_records)
    if changed.empty:
        changed = pd.DataFrame(columns=["MATCH_KEY", "SKU", "item_id", "name", "differences", "differences_text"])
    unchanged = deduped.loc[unchanged_indexes].copy() if unchanged_indexes else deduped.iloc[0:0].copy()

    blocking_records = [
        {
            "row_number": int(index) + 2 if isinstance(index, int) else index,
            "SKU": first_present(row, ["SKU", "sku"], ""),
            "issue": "duplicate target SKU",
        }
        for index, row in duplicates.iterrows()
    ]
    blocking = pd.DataFrame(blocking_records)
    if blocking.empty:
        blocking = pd.DataFrame(columns=["row_number", "SKU", "issue"])

    return {
        "target": target,
        "existing": existing,
        "missing": missing,
        "changed": changed,
        "unchanged": unchanged,
        "duplicates": duplicates,
        "blocking": blocking,
        "summary": {
            "target_rows": len(target),
            "existing_items": existing["MATCH_KEY"].nunique() if "MATCH_KEY" in existing else 0,
            "missing": len(missing),
            "changed": len(changed),
            "unchanged": len(unchanged),
            "duplicates": len(duplicates),
        },
    }


def build_inventory_item_payload(
    row: pd.Series,
    defaults: Optional[dict[str, Any]] = None,
    tax_preferences: Optional[list[dict[str, Any]]] = None,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    defaults = defaults or {}
    sku = str(first_present(row, ["SKU", "sku"], "")).strip()
    name = str(first_present(row, ["Item Name", "Name", "name"], "")).strip()
    unit = str(first_present(row, ["Usage unit", "Usage Unit", "unit"], defaults.get("unit", "NOS"))).strip() or "NOS"
    sales_description = str(first_present(row, ["Sales Description", "Description", "Item Name"], name)).strip()
    purchase_description = str(first_present(row, ["Purchase Description", "Description", "Item Name"], name)).strip()

    rate, defaulted_rate = number_or_zero(
        first_present(row, ["rate", "Rate", "Selling Price", "Sales Rate", "selling_price"], defaults.get("rate"))
    )
    purchase_rate, defaulted_purchase_rate = number_or_zero(
        first_present(
            row,
            ["purchase_rate", "Purchase Rate", "Purchase Price", "purchase_price"],
            defaults.get("purchase_rate"),
        )
    )
    opening_stock, _ = number_or_zero(first_present(row, ["Opening Stock", "initial_stock"], defaults.get("initial_stock", 0)))
    opening_stock_value, _ = number_or_zero(
        first_present(row, ["Opening Stock Value", "initial_stock_rate"], defaults.get("initial_stock_rate", 0))
    )

    if not sku:
        issues.append("missing SKU")
    if not name:
        issues.append("missing Item Name")
    if defaulted_rate:
        issues.append("selling rate defaulted to 0")
    if defaulted_purchase_rate:
        issues.append("purchase rate defaulted to 0")

    hsn_or_sac = first_present(row, ["HSN/SAC", "HSN", "hsn_or_sac", "hsn_sac"], defaults.get("hsn_or_sac"))
    if hsn_or_sac is None:
        issues.append("HSN/SAC missing")

    payload: dict[str, Any] = {
        "name": name,
        "sku": sku,
        "unit": unit,
        "description": sales_description,
        "purchase_description": purchase_description,
        "item_type": defaults.get("item_type", "inventory"),
        "product_type": defaults.get("product_type", "goods"),
        "rate": rate,
        "purchase_rate": purchase_rate,
        "account_id": str(first_present(row, ["account_id"], defaults.get("account_id", ""))).strip(),
        "purchase_account_id": str(first_present(row, ["purchase_account_id"], defaults.get("purchase_account_id", ""))).strip(),
        "inventory_account_id": str(
            first_present(row, ["inventory_account_id"], defaults.get("inventory_account_id", ""))
        ).strip(),
        "can_be_sold": defaults.get("can_be_sold", True),
        "can_be_purchased": defaults.get("can_be_purchased", True),
        "track_inventory": defaults.get("track_inventory", True),
        "is_returnable": defaults.get("is_returnable", True),
        "inventory_valuation_method": defaults.get("inventory_valuation_method", "fifo"),
        "initial_stock": opening_stock,
        "initial_stock_rate": opening_stock_value,
        "is_taxable": defaults.get("is_taxable", True),
        "item_tax_preferences": tax_preferences if tax_preferences is not None else defaults.get("item_tax_preferences", []),
    }
    if hsn_or_sac is not None:
        payload["hsn_or_sac"] = str(hsn_or_sac).strip()
    return payload, issues


def prepare_item_create_payloads(
    rows: pd.DataFrame,
    output_dir: str | Path,
    payload_builder: Any = build_inventory_item_payload,
    filename_prefix: str = "zoho_inventory_create",
    filename_suffix: str = "",
) -> dict[str, Any]:
    """Build create payloads from rows and write preview/validation outputs."""
    output_dir = Path(output_dir)
    work_rows = rows.copy()
    if "SKU" in work_rows.columns:
        work_rows = work_rows[work_rows["SKU"].notna()].copy()
        work_rows["SKU"] = work_rows["SKU"].astype(str).str.strip()
        work_rows = work_rows[work_rows["SKU"] != ""].copy()

    payload_records: list[dict[str, Any]] = []
    validation_records: list[dict[str, Any]] = []
    seen_skus: set[str] = set()
    duplicate_skus: set[str] = set()
    for index, row in work_rows.iterrows():
        payload, issues = payload_builder(row)
        sku_key = normalize_sku(payload.get("sku"))
        if sku_key and sku_key in seen_skus:
            issues.append("duplicate SKU in create sheet")
            duplicate_skus.add(payload["sku"])
        if sku_key:
            seen_skus.add(sku_key)
        payload_records.append(payload)
        validation_records.append(
            {
                "row_number": int(index) + 2 if isinstance(index, int) else index,
                "SKU": payload.get("sku", ""),
                "Item Name": payload.get("name", ""),
                "ready_for_create": not issues,
                "issues": "; ".join(issues),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    preview_json = output_dir / f"{filename_prefix}_payload_preview{filename_suffix}.json"
    preview_csv = output_dir / f"{filename_prefix}_payload_preview{filename_suffix}.csv"
    validation_xlsx = output_dir / f"{filename_prefix}_validation{filename_suffix}.xlsx"

    preview_json.write_text(json.dumps(payload_records, indent=2))
    pd.DataFrame(payload_records).to_csv(preview_csv, index=False)
    validation = pd.DataFrame(validation_records)
    if validation.empty:
        validation = pd.DataFrame(columns=["row_number", "SKU", "Item Name", "ready_for_create", "issues"])
    with pd.ExcelWriter(validation_xlsx, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Metric": [
                    "Items in create sheet",
                    "Unique SKUs in create sheet",
                    "Duplicate SKUs",
                    "Rows ready with no validation warnings",
                    "Rows with warnings",
                ],
                "Value": [
                    len(payload_records),
                    len(seen_skus),
                    len(duplicate_skus),
                    int(validation["ready_for_create"].sum()) if not validation.empty else 0,
                    int((~validation["ready_for_create"]).sum()) if not validation.empty else 0,
                ],
            }
        ).to_excel(writer, sheet_name="Summary", index=False)
        validation.to_excel(writer, sheet_name="Validation", index=False)

    blocking = validation[validation["issues"].str.contains("missing SKU|missing Item Name|duplicate SKU", na=False)]
    return {
        "payloads": payload_records,
        "validation": validation,
        "blocking": blocking,
        "paths": {
            "preview_json": preview_json,
            "preview_csv": preview_csv,
            "validation_xlsx": validation_xlsx,
        },
        "summary": {
            "items_in_create_sheet": len(payload_records),
            "unique_skus": len(seen_skus),
            "duplicate_skus": len(duplicate_skus),
            "ready_for_create": int(validation["ready_for_create"].sum()) if not validation.empty else 0,
            "rows_with_warnings": int((~validation["ready_for_create"]).sum()) if not validation.empty else 0,
        },
    }


def create_missing_inventory_items(
    client: Any,
    payloads: list[dict[str, Any]],
    output_dir: str | Path,
    results_filename: str = "zoho_inventory_create_results.csv",
) -> tuple[list[dict[str, Any]], Path]:
    """Create missing items through zoho_sdk and write a result CSV."""
    results: list[dict[str, Any]] = []
    for payload in payloads:
        print(f"Creating Zoho Inventory item {payload['sku']}...", flush=True)
        try:
            response = client.items.create(payload)
            created_item = response.get("item", response) if isinstance(response, dict) else {}
            results.append(
                {
                    "SKU": payload["sku"],
                    "status": "created",
                    "item_id": created_item.get("item_id") if isinstance(created_item, dict) else "",
                    "message": response.get("message", "") if isinstance(response, dict) else "",
                }
            )
        except Exception as exc:
            results.append({"SKU": payload["sku"], "status": "error", "item_id": "", "message": str(exc)})
            print(f"  error: {exc}", flush=True)

    results_path = Path(output_dir) / results_filename
    results_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(results_path, index=False)
    return results, results_path


def write_item_diff_outputs(
    diff: dict[str, Any],
    output_dir: str | Path,
    filename_prefix: str = "zoho_inventory_items",
    report_label: str = "Candidate",
    snapshot_filename: str = "zoho_inventory_existing_items_snapshot.csv",
    filenames: Optional[dict[str, str]] = None,
) -> dict[str, Path]:
    """Write reusable CSV/XLSX reports for an item comparison."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = diff["target"]
    existing = diff["existing"]
    missing = diff["missing"]
    changed = diff["changed"]

    names = {
        "missing_csv": f"{filename_prefix}_missing.csv",
        "missing_xlsx": f"{filename_prefix}_missing.xlsx",
        "changed_csv": f"{filename_prefix}_changed.csv",
        "changed_xlsx": f"{filename_prefix}_changed.xlsx",
        "existing_snapshot": snapshot_filename,
    }
    names.update(filenames or {})
    missing_path = output_dir / names["missing_csv"]
    missing_xlsx = output_dir / names["missing_xlsx"]
    changed_path = output_dir / names["changed_csv"]
    changed_xlsx = output_dir / names["changed_xlsx"]
    existing_path = output_dir / names["existing_snapshot"]

    missing.drop(columns=["MATCH_KEY", "SKU_KEY"], errors="ignore").to_csv(missing_path, index=False)
    existing.to_csv(existing_path, index=False)
    changed.to_csv(changed_path, index=False)

    summary = diff["summary"]
    with pd.ExcelWriter(missing_xlsx, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Metric": [
                    f"{report_label} rows",
                    "Zoho Inventory item SKUs",
                    f"Missing {report_label.lower()} rows",
                    f"Changed {report_label.lower()} rows",
                    f"Duplicate {report_label.lower()} rows",
                ],
                "Value": [
                    len(candidates),
                    summary["existing_items"],
                    summary["missing"],
                    summary["changed"],
                    summary["duplicates"],
                ],
            }
        ).to_excel(writer, sheet_name="Summary", index=False)
        missing.drop(columns=["MATCH_KEY", "SKU_KEY"], errors="ignore").to_excel(
            writer, sheet_name="Missing_Items", index=False
        )
        changed.to_excel(writer, sheet_name="Changed_Items", index=False)
        diff["duplicates"].to_excel(writer, sheet_name="Duplicate_Items", index=False)

    with pd.ExcelWriter(changed_xlsx, engine="openpyxl") as writer:
        changed.to_excel(writer, sheet_name="Changed_Items", index=False)

    return {
        "missing_csv": missing_path,
        "missing_xlsx": missing_xlsx,
        "existing_snapshot": existing_path,
        "changed_csv": changed_path,
        "changed_xlsx": changed_xlsx,
    }


def compare_items_with_inventory(
    candidates: pd.DataFrame,
    output_dir: str | Path,
    *,
    client: Any = None,
    client_factory: Any = None,
    existing_items_file: Optional[str | Path] = None,
    purchase_account_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    match_key: str = "sku",
    compare_fields: Optional[list[Any]] = None,
    filename_prefix: str = "zoho_inventory_items",
    report_label: str = "Candidate",
    snapshot_filename: str = "zoho_inventory_existing_items_snapshot.csv",
    output_filenames: Optional[dict[str, str]] = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Compare any candidate item table with Zoho Inventory and write reports.

    Existing items can come from a CSV snapshot or from an injected client.
    ``client_factory`` keeps authentication policy outside this generic module.
    """
    snapshot = Path(existing_items_file) if existing_items_file else None
    if snapshot and snapshot.exists():
        if verbose:
            print(f"Using existing Zoho Inventory snapshot: {snapshot}", flush=True)
        existing = pd.read_csv(snapshot)
        if "MATCH_KEY" not in existing.columns:
            source_column = match_key if match_key in existing.columns else "sku"
            existing["MATCH_KEY"] = existing[source_column].map(normalize_sku)
        if match_key.lower() == "sku" and "SKU_KEY" not in existing.columns:
            existing["SKU_KEY"] = existing["MATCH_KEY"]
    else:
        if client is None:
            if client_factory is None:
                raise ValueError("client or client_factory is required when no existing snapshot is available")
            client = client_factory()
        items = fetch_inventory_items(
            client,
            purchase_account_id=purchase_account_id,
            max_pages=max_pages,
            verbose=verbose,
        )
        existing = items_to_frame(items, match_key=match_key)

    diff = find_item_diff(candidates, existing, match_key=match_key, compare_fields=compare_fields)
    paths = write_item_diff_outputs(
        diff,
        output_dir,
        filename_prefix=filename_prefix,
        report_label=report_label,
        snapshot_filename=snapshot_filename,
        filenames=output_filenames,
    )
    return {
        "candidates": diff["target"],
        "existing": diff["existing"],
        "missing": diff["missing"],
        "changed": diff["changed"],
        "diff": diff,
        "paths": paths,
        "summary": diff["summary"],
    }


def prepare_inventory_items_from_sheet(
    create_xlsx: str | Path,
    output_dir: str | Path,
    *,
    sheet_name: str = "Missing_Items",
    payload_builder: Any = build_inventory_item_payload,
    filename_prefix: str = "zoho_inventory_create",
    filename_suffix: str = "",
) -> dict[str, Any]:
    """Read an item sheet and produce payload previews and validation reports."""
    rows = pd.read_excel(Path(create_xlsx), sheet_name=sheet_name)
    return prepare_item_create_payloads(
        rows,
        output_dir=output_dir,
        payload_builder=payload_builder,
        filename_prefix=filename_prefix,
        filename_suffix=filename_suffix,
    )


def create_inventory_items_from_sheet(
    create_xlsx: str | Path,
    output_dir: str | Path,
    *,
    client: Any = None,
    client_factory: Any = None,
    sheet_name: str = "Missing_Items",
    payload_builder: Any = build_inventory_item_payload,
    filename_prefix: str = "zoho_inventory_create",
    filename_suffix: str = "",
    results_filename: str = "zoho_inventory_create_results.csv",
    abort_on_blocking: bool = True,
) -> dict[str, Any]:
    """Validate an item sheet and explicitly create its items in Inventory."""
    prepared = prepare_inventory_items_from_sheet(
        create_xlsx,
        output_dir,
        sheet_name=sheet_name,
        payload_builder=payload_builder,
        filename_prefix=filename_prefix,
        filename_suffix=filename_suffix,
    )
    if abort_on_blocking and not prepared["blocking"].empty:
        raise RuntimeError(
            "Create aborted because the sheet has blocking validation issues. "
            f"Review {prepared['paths']['validation_xlsx']}."
        )
    if client is None:
        if client_factory is None:
            raise ValueError("client or client_factory is required to create Inventory items")
        client = client_factory()
    results, results_path = create_missing_inventory_items(
        client,
        prepared["payloads"],
        output_dir,
        results_filename=results_filename,
    )
    prepared["results"] = results
    prepared["paths"]["results_csv"] = results_path
    return prepared
