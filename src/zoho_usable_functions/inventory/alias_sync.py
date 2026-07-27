"""Module for syncing Gemini invoice JSON names as item alias names in Zoho Books."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from zoho_usable_functions.core.logging_config import setup_logging


def load_alias_mappings(mapping_file: str | Path) -> List[Dict[str, Any]]:
    """Load name/SKU mapping list from JSON file."""
    path = Path(mapping_file)
    if not path.exists():
        raise FileNotFoundError(f"Mapping file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Mapping file {path} must contain a JSON array.")

    return data


def group_alias_mappings(data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Group alias records by SKU.
    
    Returns a dictionary keyed by normalized SKU with item metadata and unique alias names.
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for record in data:
        sku = str(record.get("zoho_sku") or "").strip()
        json_name = str(record.get("json_name") or "").strip()
        zoho_name = str(record.get("zoho_name") or "").strip()

        if not sku or not json_name:
            continue

        sku_key = sku.casefold()

        if sku_key not in grouped:
            grouped[sku_key] = {
                "sku": sku,
                "zoho_name": zoho_name,
                "aliases": [],
            }

        if json_name not in grouped[sku_key]["aliases"]:
            grouped[sku_key]["aliases"].append(json_name)

    return grouped


def sync_item_aliases(
    books_client: Any,
    mappings: List[Dict[str, Any]],
    execute: bool = False,
    overwrite: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Search Zoho Books items by SKU and update the alias_name field with Gemini invoice names.

    :param books_client: Instantiated ZohoBooksAPI client.
    :param mappings: List of dict mappings containing 'zoho_sku', 'json_name', 'zoho_name'.
    :param execute: If True, POST updates to Zoho Books. Otherwise performs dry-run.
    :param overwrite: If True, overwrite existing non-empty alias_name in Zoho Books.
    :param verbose: Print progress info.
    :return: Summary dict with update statistics and item status list.
    """
    grouped = group_alias_mappings(mappings)
    
    summary = {
        "total_mapped_skus": len(grouped),
        "found_in_zoho": 0,
        "not_found_in_zoho": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }

    for sku_key, item_mapping in grouped.items():
        sku = item_mapping["sku"]
        aliases = item_mapping["aliases"]
        target_alias = " | ".join(aliases)

        # Search for item by SKU in Zoho Books
        try:
            res = books_client.request("GET", "items", params={"search_text": sku})
            found_items = res.get("items", [])
        except Exception as err:
            summary["errors"] += 1
            summary["details"].append({
                "sku": sku,
                "status": "error",
                "message": f"Search failed: {err}",
            })
            continue

        # Filter for exact SKU match
        matching_item = None
        for item in found_items:
            if str(item.get("sku") or "").strip().casefold() == sku_key:
                matching_item = item
                break

        if not matching_item:
            summary["not_found_in_zoho"] += 1
            summary["details"].append({
                "sku": sku,
                "status": "not_found",
                "message": f"Item SKU {sku!r} not found in Zoho Books",
            })
            continue

        summary["found_in_zoho"] += 1
        item_id = matching_item.get("item_id") or matching_item.get("id")

        # Fetch detailed item record
        try:
            detail = books_client.items.get(item_id)
            item_data = detail.get("item", {})
        except Exception as err:
            summary["errors"] += 1
            summary["details"].append({
                "sku": sku,
                "status": "error",
                "message": f"Failed to fetch item detail: {err}",
            })
            continue

        current_alias = str(item_data.get("alias_name") or "").strip()

        # Check if update is needed
        if current_alias and current_alias == target_alias:
            summary["skipped"] += 1
            summary["details"].append({
                "sku": sku,
                "item_id": item_id,
                "status": "skipped",
                "message": "alias_name already up to date",
                "current_alias": current_alias,
            })
            continue

        if current_alias and not overwrite:
            summary["skipped"] += 1
            summary["details"].append({
                "sku": sku,
                "item_id": item_id,
                "status": "skipped",
                "message": f"alias_name already set ({current_alias!r}); use --overwrite to replace",
                "current_alias": current_alias,
                "target_alias": target_alias,
            })
            continue

        # Perform or simulate update
        if execute:
            try:
                update_payload = {
                    "name": item_data["name"],
                    "alias_name": target_alias,
                }
                res = books_client.request("PUT", f"items/{item_id}", json=update_payload)
                if res.get("code") == 0:
                    summary["updated"] += 1
                    summary["details"].append({
                        "sku": sku,
                        "item_id": item_id,
                        "status": "updated",
                        "old_alias": current_alias,
                        "new_alias": target_alias,
                    })
                else:
                    summary["errors"] += 1
                    summary["details"].append({
                        "sku": sku,
                        "item_id": item_id,
                        "status": "error",
                        "message": f"Zoho error: {res.get('message')}",
                    })
            except Exception as err:
                summary["errors"] += 1
                summary["details"].append({
                    "sku": sku,
                    "item_id": item_id,
                    "status": "error",
                    "message": f"Update request failed: {err}",
                })
        else:
            # Dry-run
            summary["updated"] += 1
            summary["details"].append({
                "sku": sku,
                "item_id": item_id,
                "status": "dry_run_update",
                "old_alias": current_alias,
                "new_alias": target_alias,
            })

    return summary
