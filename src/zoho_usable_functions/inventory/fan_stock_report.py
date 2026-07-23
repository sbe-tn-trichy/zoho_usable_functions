"""Read selected fields from a FAN stock report."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from ..core.excel import read_excel_table
from .constants import FAN_STOCK_REPORT_FIELDS


_TEXT_FIELDS = {
    "sku": "SKU",
    "description": "Description",
    "status": "Status",
    "category": "CATEGORY",
    "model_group": "MODEL",
    "product_type": "Model",
    "channel": "Channel",
}
_NUMBER_FIELDS = {
    "total_stock_and_git": "Total stock +GIT",
}
_POSITIONAL_NUMBER_FIELDS = {
    "grand_stock": 79,
    "grand_git": 80,
}
def read_fan_stock_report(path: str | Path, fields: Sequence[str]) -> pd.DataFrame:
    """Return only the requested, normalized fields from a FAN stock workbook."""
    requested_fields = tuple(fields)
    unknown_fields = sorted(set(requested_fields) - set(FAN_STOCK_REPORT_FIELDS))
    if unknown_fields:
        raise ValueError(f"Unknown FAN stock report fields: {', '.join(unknown_fields)}")

    required_columns = [
        source_column
        for field, source_column in {**_TEXT_FIELDS, **_NUMBER_FIELDS}.items()
        if field in requested_fields
    ]
    report = read_excel_table(
        path,
        sheet_name="MAIN",
        header=3,
        required_columns=required_columns,
    )

    positional_fields = set(requested_fields) & _POSITIONAL_NUMBER_FIELDS.keys()
    if positional_fields:
        last_required_position = max(_POSITIONAL_NUMBER_FIELDS[field] for field in positional_fields)
        if len(report.columns) <= last_required_position:
            raise ValueError(
                f"FAN stock report requires at least {last_required_position + 1} columns; "
                f"found {len(report.columns)}"
            )

    selected = pd.DataFrame(index=report.index)
    for field in requested_fields:
        if field in _TEXT_FIELDS:
            values = report[_TEXT_FIELDS[field]]
            selected[field] = values.where(values.isna(), values.astype(str).str.strip())
        elif field in _NUMBER_FIELDS:
            selected[field] = pd.to_numeric(
                report[_NUMBER_FIELDS[field]],
                errors="coerce",
            ).fillna(0).astype(int)
        else:
            selected[field] = pd.to_numeric(
                report.iloc[:, _POSITIONAL_NUMBER_FIELDS[field]],
                errors="coerce",
            ).fillna(0).astype(int)

    return selected
