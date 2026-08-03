#!/usr/bin/env python3
"""Apply the reviewed remaining Neoseal naming, SKU, and grouping fixes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"),
)

from zoho.base_client import BaseZohoClient
from zoho_usable_functions.core.auth import get_inventory_client


CORRECTIONS: dict[str, dict[str, str]] = {
    "1094368000046220961": {"name": "516 Eco Prime 10 L"},
    "1094368000038032568": {
        "sku": "753-25",
        "category_id": "1094368000048297245",
    },
    "1094368000057751618": {"sku": "802-20"},
    "1094368000034939067": {"sku": "DRAIN-50"},
    "1094368000050559017": {"name": "SR 609 1 L"},
    "1094368000034939093": {"sku": "SARAL-GP-100-RED"},
    "1094368000035638793": {"sku": "SARAL-HSR-25-BLUE"},
    "1094368000057568779": {"sku": "200-100-UPVC-CLEAR"},
    "1094368000057589972": {
        "name": "200 UPVC Solution 100ml Clear (PVC Can)",
        "sku": "200-100-UPVC-CLEAR-COEX",
    },
    "1094368000058406002": {"name": "305 CPVC Solution 25ml (Tube)"},
    "1094368000058405330": {"name": "566 Quick Leak Stop 1kg"},
    "1094368000058423044": {
        "name": '1 1/2" PVC Ball Valve GS PLUS',
    },
    "1094368000057410669": {"sku": "10M-YELLOW-12MM-0.15"},
    "1094368000048371410": {"sku": "6M-INSULATION-BLUE"},
    "1094368000039797952": {"sku": "20-PVC-UPVC"},
    "1094368000038497584": {"name": "IWP 500 1 L"},
    "1094368000057338108": {"name": "IWP 500 5 L"},
    "1094368000036676294": {"sku": "10M-YELLOW-12MM"},
    "1094368000034939235": {"sku": "5M-YELLOW-12MM"},
    "1094368000035796470": {"sku": "10M-WHITE-19MM"},
    "1094368000036676268": {"sku": "6M-INSULATION-BLACK"},
    "1094368000037635797": {"sku": "6M-INSULATION-GREEN"},
    "1094368000037635745": {"sku": "6M-INSULATION-RED"},
    "1094368000037635771": {"sku": "6M-INSULATION-YELLOW"},
}

# Existing destination group -> item ID -> attribute option values.
SIMPLE_MOVES: dict[str, dict[str, tuple[str, ...]]] = {
    "PVC Ball Valve": {
        "1094368000055446306": ("1.25", "GSP"),
        "1094368000053443344": ("2", "GSP"),
        "1094368000057364588": ("2.5", "GSP"),
        "1094368000058423044": ("1.5", "GSP"),
    },
    "UPVC Ball Valve": {
        "1094368000047641335": ("0.75", "MS"),
        "1094368000052826785": ("1.25", "GS"),
        "1094368000050115176": ("1", "MS"),
    },
    "PTFE Tape": {
        "1094368000057410669": (),
    },
    "Insulation Tape": {
        "1094368000048371410": ("Blue",),
    },
}

# New destination group -> (attribute name, item ID -> option).
NEW_GROUPS: dict[str, tuple[str, dict[str, str]]] = {
    "Eco Prime": ("Size", {"1094368000046220961": "10 L"}),
    "Neoseal Others": (
        "Product",
        {
            "1094368000038032568": "Gasket Shellac",
            "1094368000057751618": "Neoflex",
            "1094368000034939067": "Drain Cleaner",
        },
    ),
    "SR 609": ("Size", {"1094368000050559017": "1 L"}),
    "Saral Seal": (
        "Variant",
        {
            "1094368000034939093": "GP 100g Red",
            "1094368000035638793": "HSR 25g Blue",
        },
    ),
    "Quick Leak Stop": ("Size", {"1094368000058405330": "1kg"}),
    "PVC-UPVC Solvent": ("Size", {"1094368000039797952": "20ml Tube"}),
    "SBR Latex": (
        "Size",
        {
            "1094368000057757153": "1kg",
            "1094368000057757177": "5kg",
        },
    ),
    "Terrace Coat": ("Size", {"1094368000037638900": "20 L"}),
    "Neocem": ("Size", {"1094368000038497554": "2K 3kg"}),
    "Bitucoat": (
        "Size",
        {
            "1094368000055446264": "10kg",
            "1094368000055446285": "20kg",
            "1094368000056535456": "4kg",
        },
    ),
    "Seal X": (
        "Size",
        {
            "1094368000042492335": "1kg",
            "1094368000056087379": "300g",
        },
    ),
    "IWP 500": (
        "Size",
        {
            "1094368000038497584": "1 L",
            "1094368000057338108": "5 L",
        },
    ),
    "ND-40 Lubricant": (
        "Volume",
        {
            "1094368000035796442": "100ml",
            "1094368000046220923": "50ml",
        },
    ),
}

SOLVENT_ADDITIONS: dict[str, dict[str, tuple[str, str, str]]] = {
    "UPVC Solvent": {
        "1094368000052101060": ("200", "100ml", "Blue PVC Can"),
        "1094368000057568779": ("200", "100ml", "Clear Tin"),
        "1094368000057589972": ("200", "100ml", "Clear PVC Can"),
        "1094368000052101140": ("205", "118ml", "Blue PVC Can"),
        "1094368000052101100": ("205", "59ml", "Blue PVC Can"),
    },
    "CPVC Solvent": {
        "1094368000052101180": ("305", "118", "PVC Can"),
        "1094368000058406002": ("305", "25", "Tube"),
    },
}


def _desired(item_id: str, detail: dict[str, Any], field: str) -> str:
    return CORRECTIONS.get(item_id, {}).get(field, str(detail.get(field) or ""))


def _common(details: list[dict[str, Any]], *fields: str) -> str:
    for field in fields:
        values = {
            str(detail.get(field) or "").strip()
            for detail in details
            if detail.get(field)
        }
        if len(values) == 1:
            return values.pop()
        if len(values) > 1:
            raise ValueError(f"Items have inconsistent {field} values: {values}")
    return ""


def _optional_common(details: list[dict[str, Any]], field: str) -> str:
    values = {
        str(detail.get(field) or "").strip()
        for detail in details
        if detail.get(field)
    }
    return values.pop() if len(values) == 1 else ""


def _update_grouping(
    client: Any, group_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Update an existing group; the SDK currently exposes creation only."""
    return BaseZohoClient.request(
        client,
        method="PUT",
        endpoint=f"items/grouping/{group_id}",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        data={"JSONString": json.dumps(payload)},
        params={"organization_id": client.organization_id},
    )


def _new_group_payload(
    group_name: str,
    attribute_name: str,
    variants: dict[str, str],
    details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = [details[item_id] for item_id in variants]
    payload: dict[str, Any] = {
        "group_name": group_name,
        "unit": _common(selected, "unit") or "NOS",
        "purchase_account_id": _common(selected, "purchase_account_id"),
        "account_id": _common(selected, "account_id", "sales_account_id"),
        "inventory_account_id": _common(selected, "inventory_account_id"),
        "attribute_name1": attribute_name,
        "items": [
            {
                "item_id": item_id,
                "name": _desired(item_id, details[item_id], "name"),
                "sku": _desired(item_id, details[item_id], "sku"),
                "attribute_option_name1": option,
            }
            for item_id, option in variants.items()
        ],
    }
    category_id = _optional_common(selected, "category_id")
    if category_id:
        payload["category_id"] = category_id
    missing = [
        key
        for key in ("purchase_account_id", "account_id", "inventory_account_id")
        if not payload[key]
    ]
    if missing:
        raise ValueError(f"{group_name} is missing: {', '.join(missing)}")
    return payload


def _solvent_payload(
    group: dict[str, Any],
    additions: dict[str, tuple[str, str, str]],
    details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    items = []
    for item in group.get("items", []):
        items.append(
            {
                "item_id": str(item["item_id"]),
                "name": item["name"],
                "sku": item["sku"],
                "attribute_option_name1": item.get("attribute_option_name1", ""),
                "attribute_option_name2": item.get("attribute_option_name2", ""),
                "attribute_option_name3": "Blue Tin"
                if group["group_name"] == "UPVC Solvent"
                else "Tin",
            }
        )
    for item_id, options in additions.items():
        items.append(
            {
                "item_id": item_id,
                "name": _desired(item_id, details[item_id], "name"),
                "sku": _desired(item_id, details[item_id], "sku"),
                "attribute_option_name1": options[0],
                "attribute_option_name2": options[1],
                "attribute_option_name3": options[2],
            }
        )
    return {
        "group_id": group["group_id"],
        "group_name": group["group_name"],
        "unit": group["unit"],
        "purchase_account_id": group["purchase_account_id"],
        "account_id": group["account_id"],
        "inventory_account_id": group["inventory_account_id"],
        "category_id": group.get("category_id", ""),
        "attribute_name1": group["attribute_name1"],
        "attribute_name2": group["attribute_name2"],
        "attribute_name3": "Variant",
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply all reviewed remaining Neoseal anomaly corrections."
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    client = get_inventory_client(allow_books_token=True)
    groups = client.item_groups.list_all(
        params={"filter_by": "Status.Active"}, resource_key="itemgroups"
    )
    group_ids = {
        str(group.get("group_name") or group.get("name")): str(
            group.get("group_id") or group.get("item_group_id")
        )
        for group in groups
    }
    expected_existing = set(SIMPLE_MOVES) | set(SOLVENT_ADDITIONS)
    missing_groups = sorted(expected_existing - set(group_ids))
    if missing_groups:
        raise ValueError("Existing groups were not found: " + ", ".join(missing_groups))
    target_ids = set(CORRECTIONS)
    for moves in SIMPLE_MOVES.values():
        target_ids.update(moves)
    for _, variants in NEW_GROUPS.values():
        target_ids.update(variants)
    for additions in SOLVENT_ADDITIONS.values():
        target_ids.update(additions)

    details: dict[str, dict[str, Any]] = {}
    for item_id in sorted(target_ids):
        response = client.items.get(item_id)
        details[item_id] = response.get("item", response)

    detailed_groups = {
        name: client.item_groups.get(group_ids[name]).get("item_group", {})
        for name in expected_existing
    }
    pending_new_groups = {}
    for name, definition in NEW_GROUPS.items():
        _, variants = definition
        completed = all(
            str(details[item_id].get("group_name") or "").casefold()
            == name.casefold()
            for item_id in variants
        )
        if not completed:
            pending_new_groups[name] = definition
    new_payloads = {
        name: _new_group_payload(name, attribute, variants, details)
        for name, (attribute, variants) in pending_new_groups.items()
    }
    pending_solvents = {
        name: additions
        for name, additions in SOLVENT_ADDITIONS.items()
        if detailed_groups[name].get("attribute_name3") != "Variant"
        or not set(additions).issubset(
            {
                str(item.get("item_id"))
                for item in detailed_groups[name].get("items", [])
            }
        )
    }
    solvent_payloads = {
        name: _solvent_payload(detailed_groups[name], additions, details)
        for name, additions in pending_solvents.items()
    }

    changes = {
        item_id: {
            field: value
            for field, value in desired.items()
            if str(details[item_id].get(field) or "") != value
        }
        for item_id, desired in CORRECTIONS.items()
    }
    changes = {item_id: values for item_id, values in changes.items() if values}
    pending_moves = {
        group_name: {
            item_id: options
            for item_id, options in items.items()
            if str(details[item_id].get("group_id") or "") != group_ids[group_name]
        }
        for group_name, items in SIMPLE_MOVES.items()
    }
    pending_moves = {
        group_name: items
        for group_name, items in pending_moves.items()
        if items
    }
    move_count = sum(len(items) for items in pending_moves.values())
    print(
        f"Validated {len(target_ids)} items: {len(changes)} item updates, "
        f"{move_count} moves, {len(new_payloads)} new groups, "
        f"{len(solvent_payloads)} solvent group expansions."
    )
    for item_id, update in changes.items():
        print(f"UPDATE {item_id}: {update}")
    for name, items in pending_moves.items():
        print(f"MOVE {len(items)} -> {name}")
    for name, payload in new_payloads.items():
        print(f"CREATE {name}: {len(payload['items'])} variants")
    for name, payload in solvent_payloads.items():
        print(f"EXPAND {name}: {len(payload['items'])} total variants")

    if not args.execute:
        print("Dry run only. Use --execute to apply the validated batch.")
        return

    for item_id, update in changes.items():
        client.items.update(item_id, update)
        print(f"Updated item {item_id}")
        time.sleep(0.25)

    for group_name, items in pending_moves.items():
        group = detailed_groups[group_name]
        attribute_names = [
            group.get("attribute_name1"),
            group.get("attribute_name2"),
            group.get("attribute_name3"),
        ]
        for item_id, options in items.items():
            payload: dict[str, Any] = {"group_id": group_ids[group_name]}
            for index, option in enumerate(options, start=1):
                payload[f"attribute_name{index}"] = attribute_names[index - 1]
                payload[f"attribute_option_name{index}"] = option
            client.request("PUT", f"items/move/{item_id}", json=payload)
            print(f"Moved {item_id} -> {group_name}")
            time.sleep(0.25)

    for group_name, payload in solvent_payloads.items():
        group_id = group_ids[group_name]
        _update_grouping(client, group_id, payload)
        print(f"Expanded {group_name}")
        time.sleep(0.5)

    for group_name, payload in new_payloads.items():
        response = client.items.group_items(payload)
        group = response.get("item_group", response)
        print(
            f"Created {group_name}: "
            f"{group.get('group_id') or group.get('item_group_id') or 'ID not returned'}"
        )
        time.sleep(0.5)


if __name__ == "__main__":
    main()
