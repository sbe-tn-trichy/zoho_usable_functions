#!/usr/bin/env python3
"""Generate Price and Margin Analysis report grouped by Item Group and Category for Neoseal items.

Category Order:
1. PVC Solvent
2. UPVC Solvent
3. Solvent Others
4. CPVC Solvent
5. PVC Ball Valve
6. UPVC Ball Valve
7. PTFE Tape
8. Crack Filler
9. Others
10. Water Proofing

Automatically fixes Sales Price (SP) for any items with Original Margin (%) < 10.0%:
Formula:
    Gross MRP = round(1.18 * 1.17 * CP)
    Fixed SP = round(Gross MRP / 1.18, 2)
    Net Price = round(1.18 * Fixed SP, 2)
"""

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

INPUT_CSV = REPO_ROOT / "output" / "inventory" / "neoseal_items_active.csv"
OUTPUT_CSV = REPO_ROOT / "output" / "inventory" / "neoseal_price_margin_analysis.csv"
OUTPUT_XLSX = (
    REPO_ROOT / "output" / "inventory" / "neoseal_price_margin_analysis.xlsx"
)

# Threshold for margin % fix
MARGIN_THRESHOLD_PCT = 10.0

# Master Category Order
CATEGORY_ORDER = [
    "PVC Solvent",
    "UPVC Solvent",
    "Solvent Others",
    "CPVC Solvent",
    "PVC Ball Valve",
    "UPVC Ball Valve",
    "PTFE Tape",
    "Crack Filler",
    "Others",
    "Water Proofing",
]

# Mapping from specific Item Group Name to Category
GROUP_TO_CATEGORY = {
    "PVC Solvent": "PVC Solvent",
    "UPVC Solvent": "UPVC Solvent",
    "Solvent Others": "Solvent Others",
    "CPVC Solvent": "CPVC Solvent",
    "PVC Ball Valve": "PVC Ball Valve",
    "UPVC Ball Valve": "UPVC Ball Valve",
    "PTFE Tape": "PTFE Tape",
    "Crack Filler": "Crack Filler",
    # Others
    "Insulation Tape": "Others",
    "ND-40 Lubricant": "Others",
    "Neoseal Others": "Others",
    "SR 609": "Others",
    "Saral Seal": "Others",
    # Water Proofing
    "Bitucoat": "Water Proofing",
    "Damp Kill": "Water Proofing",
    "Eco Prime": "Water Proofing",
    "GP Silicone Sealant": "Water Proofing",
    "IWP 500": "Water Proofing",
    "Neocem": "Water Proofing",
    "Quick Leak Stop": "Water Proofing",
    "SBR Latex": "Water Proofing",
    "Seal X": "Water Proofing",
    "Terrace Coat": "Water Proofing",
}


def calc_fixed_sp(cp: float) -> float:
    """Calculate fixed Sales Price (SP).

    Formula:
        Gross = round(1.18 * 1.17 * CP)
        SP = round(Gross / 1.18, 2)
    """
    gross = round(1.18 * 1.17 * cp)
    return round(gross / 1.18, 2)


def main():
    if not INPUT_CSV.exists():
        alt_input = (
            REPO_ROOT.parent / "output" / "inventory" / "neoseal_items_active.csv"
        )
        if alt_input.exists():
            input_path = alt_input
        else:
            raise FileNotFoundError(f"Input file {INPUT_CSV} not found.")
    else:
        input_path = INPUT_CSV

    df = pd.read_csv(input_path)

    # Handle missing or empty group_name
    df["group_name"] = df["group_name"].fillna("[No Group]").replace("", "[No Group]")

    # Map Category
    df["category"] = df["group_name"].map(
        lambda g: GROUP_TO_CATEGORY.get(g, "Others")
    )

    # Ensure numeric rate and purchase_rate
    df["SP_Original"] = pd.to_numeric(df["rate"], errors="coerce").fillna(0.0)
    df["CP"] = pd.to_numeric(df["purchase_rate"], errors="coerce").fillna(0.0)

    # Calculate original margin %
    df["Original_Margin_Pct"] = np.where(
        df["SP_Original"] > 0,
        ((df["SP_Original"] - df["CP"]) / df["SP_Original"] * 100).round(2),
        0.0,
    )

    # Condition to fix SP: Original Margin % < 10.0% (or SP <= CP)
    def should_fix(row):
        sp_orig = row["SP_Original"]
        cp = row["CP"]
        if cp <= 0:
            return False
        orig_pct = row["Original_Margin_Pct"]
        return orig_pct < MARGIN_THRESHOLD_PCT

    df["Is_SP_Fixed"] = df.apply(should_fix, axis=1)
    df["SP_Fixed"] = df.apply(
        lambda row: calc_fixed_sp(row["CP"]) if row["Is_SP_Fixed"] else row["SP_Original"],
        axis=1,
    )

    # Calculate Net Price (Rs) = 1.18 * Fixed SP
    df["Net_Price_Rs"] = (1.18 * df["SP_Fixed"]).round(2)

    # Calculate Margin (Rs) and Margin (%) using SP_Fixed
    df["Margin_Rs"] = (df["SP_Fixed"] - df["CP"]).round(2)
    df["Margin_Pct"] = np.where(
        df["SP_Fixed"] > 0,
        ((df["SP_Fixed"] - df["CP"]) / df["SP_Fixed"] * 100).round(2),
        0.0,
    )

    # Select and order columns for the analysis sheet
    analysis_df = df[
        [
            "category",
            "group_name",
            "sku",
            "name",
            "SP_Original",
            "SP_Fixed",
            "Net_Price_Rs",
            "CP",
            "Margin_Rs",
            "Margin_Pct",
            "Is_SP_Fixed",
            "stock_on_hand",
            "unit",
            "item_id",
        ]
    ].copy()

    # Rename columns for clarity
    analysis_df.columns = [
        "Category",
        "Group Name",
        "SKU",
        "Item Name",
        "Original SP (Rs)",
        "Fixed SP (Rs)",
        "Net Price (Rs)",
        "CP (Rs)",
        "Margin (Rs)",
        "Margin (%)",
        "SP Fixed?",
        "Stock on Hand",
        "Unit",
        "Item ID",
    ]

    # Categorical type for strict custom group ordering
    cat_type = pd.CategoricalDtype(categories=CATEGORY_ORDER, ordered=True)
    analysis_df["Category_Order"] = analysis_df["Category"].astype(cat_type)

    # Sort by Category Order, then Group Name, then Item Name
    analysis_df = analysis_df.sort_values(
        by=["Category_Order", "Group Name", "Item Name"]
    ).reset_index(drop=True)

    # Drop temporary sort column
    final_df = analysis_df.drop(columns=["Category_Order"])

    # Export to CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Successfully generated CSV: {OUTPUT_CSV}")

    # Export to Excel with multiple sheets
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        final_df.to_excel(writer, sheet_name="Price & Margin Analysis", index=False)

        # Summary Sheet per Category (Ordered)
        cat_summary = (
            final_df.groupby("Category", observed=False)
            .agg(
                Item_Count=("SKU", "count"),
                Fixed_Items=("SP Fixed?", lambda x: x.sum()),
                Avg_SP=("Fixed SP (Rs)", "mean"),
                Avg_Net_Price=("Net Price (Rs)", "mean"),
                Avg_CP=("CP (Rs)", "mean"),
                Avg_Margin_Rs=("Margin (Rs)", "mean"),
                Avg_Margin_Pct=("Margin (%)", "mean"),
                Total_Stock=("Stock on Hand", "sum"),
            )
            .round(2)
            .reindex(CATEGORY_ORDER)
            .reset_index()
        )
        cat_summary.columns = [
            "Category",
            "Item Count",
            "Fixed Items Count",
            "Avg SP (Rs)",
            "Avg Net Price (Rs)",
            "Avg CP (Rs)",
            "Avg Margin (Rs)",
            "Avg Margin (%)",
            "Total Stock",
        ]
        cat_summary.to_excel(writer, sheet_name="Category Summary", index=False)

        # Summary Sheet per Group
        group_summary = (
            final_df.groupby("Group Name")
            .agg(
                Category=("Category", "first"),
                Item_Count=("SKU", "count"),
                Fixed_Items=("SP Fixed?", lambda x: x.sum()),
                Avg_SP=("Fixed SP (Rs)", "mean"),
                Avg_Net_Price=("Net Price (Rs)", "mean"),
                Avg_CP=("CP (Rs)", "mean"),
                Avg_Margin_Rs=("Margin (Rs)", "mean"),
                Avg_Margin_Pct=("Margin (%)", "mean"),
                Total_Stock=("Stock on Hand", "sum"),
            )
            .round(2)
            .reset_index()
        )
        group_summary.columns = [
            "Group Name",
            "Category",
            "Item Count",
            "Fixed Items Count",
            "Avg SP (Rs)",
            "Avg Net Price (Rs)",
            "Avg CP (Rs)",
            "Avg Margin (Rs)",
            "Avg Margin (%)",
            "Total Stock",
        ]
        group_summary.to_excel(writer, sheet_name="Group Summary", index=False)

    print(f"Successfully generated XLSX: {OUTPUT_XLSX}")
    print(f"Total items analyzed: {len(final_df)}")
    fixed_count = final_df["SP Fixed?"].sum()
    print(f"Items with fixed Sales Price (Margin < 10%): {fixed_count}")


if __name__ == "__main__":
    main()
