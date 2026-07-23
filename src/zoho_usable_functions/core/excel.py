"""Reusable helpers for reading Excel workbooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pandas as pd


def read_excel_table(
    path: str | Path,
    *,
    sheet_name: str | int = 0,
    header: int | list[int] | None = 0,
    required_columns: Sequence[str] = (),
    drop_empty_rows: bool = True,
    **read_kwargs: Any,
) -> pd.DataFrame:
    """Read one worksheet and optionally validate its tabular structure.

    Additional keyword arguments are passed directly to ``pandas.read_excel``.
    """
    workbook_path = Path(path)
    frame = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        header=header,
        **read_kwargs,
    )

    if drop_empty_rows:
        frame = frame.dropna(how="all")

    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(
            f"Worksheet {sheet_name!r} in {workbook_path} is missing required columns: {missing}"
        )

    return frame
