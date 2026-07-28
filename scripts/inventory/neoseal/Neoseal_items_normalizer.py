#!/usr/bin/env python3
"""Audit Neoseal item naming, grouping, and SKU terminology anomalies."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"),
)

from zoho_usable_functions.inventory.neoseal_groups import neoseal_group_name
from zoho_usable_functions.inventory.price_list import PRICE_LIST_CSV_COLUMNS


DEFAULT_SOURCE = Path(
    "output/inventory/price_lists/neoseal_purchase/price_list.csv"
)
DEFAULT_OUTPUT = Path(
    "output/inventory/price_lists/neoseal_purchase/neoseal_item_anomalies.csv"
)

REPORT_COLUMNS = (
    *PRICE_LIST_CSV_COLUMNS,
    "Expected Group",
    "Anomaly Areas",
    "Anomaly Count",
    "Anomaly Details",
)

_SKU_GROUP_TERMS = {
    "PVC Ball Valve": "PVC",
    "UPVC Ball Valve": "UPVC",
    "PVC Solvent": "PVC",
    "UPVC Solvent": "UPVC",
    "CPVC Solvent": "CPVC",
}


def _text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _naming_anomalies(raw_name: Any) -> list[str]:
    name = _text(raw_name)
    issues: list[str] = []
    if not name:
        return ["missing item name"]
    if str(raw_name) != name:
        issues.append("leading or trailing whitespace")
    if re.search(r"\s{2,}", name):
        issues.append("repeated whitespace")
    letters = re.sub(r"[^A-Za-z]", "", name)
    if len(letters) >= 5 and letters == letters.upper():
        issues.append("item name is all uppercase")
    if re.search(r"\bDemp Kill\b", name, flags=re.IGNORECASE):
        issues.append("use 'Damp Kill', not 'Demp Kill'")
    if re.search(r"\b\d+\s*LTR\b", name):
        issues.append("use 'L' instead of 'LTR'")
    return issues


def _grouping_anomalies(current_group: Any, expected_group: str | None) -> list[str]:
    current = _text(current_group)
    if not expected_group:
        return ["item name does not match a configured Neoseal product family"]
    if not current:
        return [f"missing group; expected '{expected_group}'"]
    if current.casefold() != expected_group.casefold():
        return [f"group is '{current}'; expected '{expected_group}'"]
    return []


def _sku_anomalies(
    raw_sku: Any,
    item_name: str,
    expected_group: str | None,
    *,
    duplicate: bool,
) -> list[str]:
    sku = _text(raw_sku)
    issues: list[str] = []
    if not sku:
        return ["missing SKU"]
    if str(raw_sku) != sku:
        issues.append("leading or trailing whitespace")
    if re.search(r"\s", sku):
        issues.append("SKU contains whitespace; use hyphen-delimited terminology")
    if any(character.isalpha() and character.islower() for character in sku):
        issues.append("SKU contains lowercase letters; use uppercase")
    if re.search(r"[^A-Za-z0-9.\-\s]", sku):
        issues.append("SKU contains non-standard punctuation")
    if duplicate:
        issues.append("duplicate SKU")

    model_match = re.match(r"^(\d{3})\b", item_name)
    if model_match and not sku.upper().startswith(model_match.group(1)):
        issues.append(f"SKU should start with product code {model_match.group(1)}")

    expected_term = _SKU_GROUP_TERMS.get(expected_group or "")
    if expected_term and expected_term not in re.split(r"[-.\s]+", sku.upper()):
        issues.append(f"SKU is missing {expected_term} family terminology")
    return issues


def audit_neoseal_items(items: pd.DataFrame) -> pd.DataFrame:
    """Return only Neoseal items with naming, grouping, or SKU anomalies."""

    missing_columns = [
        column for column in PRICE_LIST_CSV_COLUMNS if column not in items.columns
    ]
    if missing_columns:
        raise ValueError(
            "Neoseal audit requires these columns: " + ", ".join(missing_columns)
        )
    if items.empty:
        raise ValueError("The Neoseal price list is empty")

    working = items.loc[:, PRICE_LIST_CSV_COLUMNS].copy()
    normalized_skus = working["SKU"].map(_text).str.casefold()
    duplicate_skus = normalized_skus.ne("") & normalized_skus.duplicated(keep=False)
    rows: list[dict[str, Any]] = []

    for position, (_, item) in enumerate(working.iterrows()):
        name = _text(item["Item Name"])
        expected_group = neoseal_group_name(name)
        naming = _naming_anomalies(item["Item Name"])
        grouping = _grouping_anomalies(item["Group Name"], expected_group)
        sku = _sku_anomalies(
            item["SKU"],
            name,
            expected_group,
            duplicate=bool(duplicate_skus.iloc[position]),
        )
        areas = [
            area
            for area, issues in (
                ("naming", naming),
                ("grouping", grouping),
                ("sku", sku),
            )
            if issues
        ]
        if not areas:
            continue

        detail_groups = [
            f"{'SKU' if area == 'sku' else area.title()}:\n"
            + "\n".join(f"- {issue}" for issue in issues)
            for area, issues in (
                ("naming", naming),
                ("grouping", grouping),
                ("sku", sku),
            )
            if issues
        ]
        row = item.to_dict()
        row.update(
            {
                "Expected Group": expected_group or "",
                "Anomaly Areas": "; ".join(areas),
                "Anomaly Count": len(naming) + len(grouping) + len(sku),
                "Anomaly Details": "\n\n".join(detail_groups),
            }
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=REPORT_COLUMNS).sort_values(
        ["Anomaly Count", "Item Name"],
        ascending=[False, True],
        kind="stable",
        ignore_index=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Find Neoseal item naming, grouping, and SKU terminology anomalies. "
            "No source data or Zoho records are changed."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        default=DEFAULT_SOURCE,
        help=f"Price-list CSV to audit (default: {DEFAULT_SOURCE}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Anomaly report CSV to create (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()

    if args.source.suffix.lower() != ".csv":
        raise ValueError("The Neoseal source must be a .csv file")
    if args.output.suffix.lower() != ".csv":
        raise ValueError("The anomaly report must use the .csv extension")
    if args.source.resolve() == args.output.resolve():
        raise ValueError("The anomaly report must be different from the source CSV")

    source = pd.read_csv(
        args.source,
        dtype={"Group Name": str, "Item Name": str, "SKU": str, "ItemId": str},
        keep_default_na=False,
    )
    anomalies = audit_neoseal_items(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    anomalies.to_csv(args.output, index=False)

    area_counts = {
        area: int(anomalies["Anomaly Areas"].str.contains(area).sum())
        for area in ("naming", "grouping", "sku")
    }
    print(f"Created Neoseal anomaly report: {args.output}")
    print(
        f"Items checked: {len(source)} | items with anomalies: {len(anomalies)} | "
        f"naming: {area_counts['naming']} | grouping: {area_counts['grouping']} | "
        f"SKU: {area_counts['sku']}"
    )
    print("No source data or Zoho records were changed.")


if __name__ == "__main__":
    main()
