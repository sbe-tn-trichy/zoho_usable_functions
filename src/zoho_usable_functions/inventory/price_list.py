"""Generate auditable price lists while enforcing a minimum gross margin."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd


@dataclass(frozen=True)
class PriceListPolicy:
    """Rules used to assess and, where necessary, increase selling prices."""

    minimum_margin_percent: Decimal = Decimal("15")
    expected_discount_percent: Decimal = Decimal("0")
    rounding_increment: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        minimum_margin = _decimal(self.minimum_margin_percent)
        discount = _decimal(self.expected_discount_percent)
        increment = _decimal(self.rounding_increment)
        if not Decimal("0") <= minimum_margin < Decimal("100"):
            raise ValueError("minimum_margin_percent must be at least 0 and below 100")
        if not Decimal("0") <= discount < Decimal("100"):
            raise ValueError("expected_discount_percent must be at least 0 and below 100")
        if increment <= 0:
            raise ValueError("rounding_increment must be greater than 0")


@dataclass(frozen=True)
class PriceListColumns:
    """Source column names. Common Zoho-style names are detected by default."""

    purchase_account: str | None = None
    sku: str | None = None
    name: str | None = None
    cost: str | None = None
    price: str | None = None


@dataclass(frozen=True)
class PriceListResult:
    price_list: pd.DataFrame
    adjustments: pd.DataFrame
    blocked: pd.DataFrame
    summary: dict[str, Any]
    policy: PriceListPolicy
    source_columns: dict[str, str]


_ALIASES = {
    "purchase_account": (
        "Purchase Account",
        "Purchase Account Name",
        "purchase_account_name",
        "Purchase Account ID",
        "purchase_account_id",
    ),
    "sku": ("SKU", "sku", "Item SKU", "Item Code", "item_code"),
    "name": ("Item Name", "name", "Name", "item_name", "Description"),
    "cost": (
        "Landed Cost",
        "Cost Price",
        "Purchase Rate",
        "purchase_rate",
        "Purchase Price",
        "cost",
    ),
    "price": (
        "Selling Price",
        "Sales Rate",
        "Rate",
        "rate",
        "List Price",
        "MRP",
    ),
}

BOOKS_PRICE_LIST_FIELDS = (
    "group_name",
    "item_id",
    "name",
    "item_name",
    "category_name",
    "unit",
    "status",
    "rate",
    "purchase_rate",
    "mrp",
)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    try:
        number = _decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _resolve_column(frame: pd.DataFrame, field: str, requested: str | None) -> str:
    if requested:
        if requested not in frame.columns:
            raise ValueError(f"Source column {requested!r} was not found")
        return requested
    for candidate in _ALIASES[field]:
        if candidate in frame.columns:
            return candidate
    aliases = ", ".join(repr(value) for value in _ALIASES[field])
    raise ValueError(f"Could not detect the {field} column; expected one of: {aliases}")


def _round_up(value: Decimal, increment: Decimal) -> Decimal:
    units = (value / increment).to_integral_value(rounding=ROUND_CEILING)
    return units * increment


def _minimum_list_price(cost: Decimal, policy: PriceListPolicy) -> Decimal:
    margin_factor = Decimal("1") - _decimal(policy.minimum_margin_percent) / Decimal("100")
    discount_factor = Decimal("1") - _decimal(policy.expected_discount_percent) / Decimal("100")
    return _round_up(cost / margin_factor / discount_factor, _decimal(policy.rounding_increment))


def _margin_percent(cost: Decimal, effective_price: Decimal) -> Decimal:
    if effective_price == 0:
        return Decimal("0")
    return (effective_price - cost) / effective_price * Decimal("100")


def generate_price_list(
    source: pd.DataFrame,
    *,
    purchase_account: str,
    policy: PriceListPolicy | None = None,
    columns: PriceListColumns | None = None,
    source_output_columns: Iterable[str] | None = None,
    inventory_tracked_only: bool = False,
    item_transform: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> PriceListResult:
    """Assess source prices and increase only prices below the policy margin.

    The margin is calculated after the expected discount:
    ``(effective selling price - cost) / effective selling price``.
    Only rows belonging to ``purchase_account`` are assessed. Rows with invalid
    identifiers, costs, or prices are blocked and never assigned a proposed price.
    """

    policy = policy or PriceListPolicy()
    columns = columns or PriceListColumns()
    if source.empty:
        raise ValueError("The source price table is empty")

    requested_account = str(purchase_account).strip()
    if not requested_account:
        raise ValueError("purchase_account is required; analyze exactly one account per run")

    resolved = {
        field: _resolve_column(source, field, getattr(columns, field))
        for field in ("purchase_account", "sku", "name", "cost", "price")
    }
    account_values = source[resolved["purchase_account"]].fillna("").astype(str).str.strip()
    account_mask = account_values.str.casefold() == requested_account.casefold()
    selected = source.loc[account_mask].copy()
    if selected.empty:
        available_accounts = sorted(value for value in account_values.unique() if value)
        preview = ", ".join(available_accounts[:10]) or "none"
        raise ValueError(
            f"Purchase account {requested_account!r} was not found. "
            f"Available purchase accounts: {preview}"
        )
    account_row_count = len(selected)
    excluded_non_inventory_items = 0
    if inventory_tracked_only:
        tracking_column = next(
            (
                candidate
                for candidate in ("track_inventory", "Track Inventory", "is_inventory_tracked")
                if candidate in selected.columns
            ),
            None,
        )
        if tracking_column is None:
            raise ValueError(
                "Inventory-tracked filtering requires a track_inventory column"
            )
        tracked_values = selected[tracking_column].map(
            lambda value: value is True
            or str(value).strip().casefold() in {"true", "1", "yes"}
        )
        selected = selected.loc[tracked_values].copy()
        excluded_non_inventory_items = account_row_count - len(selected)
        if selected.empty:
            raise ValueError(
                f"Purchase account {requested_account!r} has no inventory-tracked items"
            )
    if item_transform is not None:
        transformed = item_transform(selected)
        if len(transformed) != len(selected):
            raise ValueError("item_transform must not add or remove price-list rows")
        selected = transformed

    discount_factor = Decimal("1") - _decimal(policy.expected_discount_percent) / Decimal("100")

    normalized_skus = selected[resolved["sku"]].fillna("").astype(str).str.strip().str.upper()
    duplicate_skus = set(normalized_skus[normalized_skus.ne("") & normalized_skus.duplicated(keep=False)])
    rows: list[dict[str, Any]] = []

    for index, source_row in selected.iterrows():
        row = source_row.to_dict()
        sku = str(row.get(resolved["sku"], "") or "").strip()
        name = str(row.get(resolved["name"], "") or "").strip()
        cost = _optional_decimal(row.get(resolved["cost"]))
        current_price = _optional_decimal(row.get(resolved["price"]))
        issues: list[str] = []

        if not sku:
            issues.append("missing SKU")
        elif sku.upper() in duplicate_skus:
            issues.append("duplicate SKU")
        if not name:
            issues.append("missing item name")
        if cost is None:
            issues.append("invalid or missing cost")
        elif cost < 0:
            issues.append("cost cannot be negative")
        if current_price is None:
            issues.append("invalid or missing selling price")
        elif current_price <= 0:
            issues.append("selling price must be greater than 0")

        output = (
            {field: row.get(field) for field in source_output_columns}
            if source_output_columns is not None
            else dict(row)
        )
        output["Validation Issues"] = "; ".join(issues)

        if issues:
            output.update(
                {
                    "Effective Current Price": None,
                    "Current Margin %": None,
                    "Minimum Safe Price": None,
                    "Proposed Price": None,
                    "Proposed Margin %": None,
                    "Price Adjustment": None,
                    "Price Status": "blocked",
                }
            )
            rows.append(output)
            continue

        assert cost is not None and current_price is not None
        effective_current = current_price * discount_factor
        current_margin = _margin_percent(cost, effective_current)
        minimum_price = _minimum_list_price(cost, policy)
        proposed_price = max(current_price, minimum_price)
        effective_proposed = proposed_price * discount_factor
        proposed_margin = _margin_percent(cost, effective_proposed)
        adjustment = proposed_price - current_price
        status = "adjusted_low_margin" if adjustment > 0 else "margin_ok"

        output.update(
            {
                "Effective Current Price": float(effective_current),
                "Current Margin %": float(current_margin),
                "Minimum Safe Price": float(minimum_price),
                "Proposed Price": float(proposed_price),
                "Proposed Margin %": float(proposed_margin),
                "Price Adjustment": float(adjustment),
                "Price Status": status,
            }
        )
        rows.append(output)

    price_list = pd.DataFrame(rows)
    adjustments = price_list[price_list["Price Status"] == "adjusted_low_margin"].copy()
    blocked = price_list[price_list["Price Status"] == "blocked"].copy()
    summary = {
        "total_rows": len(price_list),
        "margin_ok": int((price_list["Price Status"] == "margin_ok").sum()),
        "adjusted_low_margin": len(adjustments),
        "blocked": len(blocked),
        "total_price_increase": float(adjustments["Price Adjustment"].sum()) if not adjustments.empty else 0.0,
        "minimum_margin_percent": float(_decimal(policy.minimum_margin_percent)),
        "expected_discount_percent": float(_decimal(policy.expected_discount_percent)),
        "rounding_increment": float(_decimal(policy.rounding_increment)),
        "purchase_account": requested_account,
        "inventory_tracked_only": inventory_tracked_only,
        "excluded_non_inventory_items": excluded_non_inventory_items,
    }
    return PriceListResult(price_list, adjustments, blocked, summary, policy, resolved)


def read_price_source(path: str | Path, *, sheet_name: str | int = 0) -> pd.DataFrame:
    """Read a CSV or Excel price source."""

    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(source_path, sheet_name=sheet_name)
    raise ValueError("Price source must be a .csv, .xlsx, or .xls file")


def write_price_list(result: PriceListResult, output_path: str | Path) -> Path:
    """Write the complete audit workbook, including adjustments and blocked rows."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".xlsx":
        raise ValueError("Price-list output must use the .xlsx extension")
    destination.parent.mkdir(parents=True, exist_ok=True)
    summary_frame = pd.DataFrame(
        {"Metric": list(result.summary), "Value": list(result.summary.values())}
    )
    policy_frame = pd.DataFrame(
        {
            "Setting": [
                "minimum_margin_percent",
                "expected_discount_percent",
                "rounding_increment",
                "purchase_account",
                "purchase_account_column",
                "sku_column",
                "name_column",
                "cost_column",
                "price_column",
            ],
            "Value": [
                result.policy.minimum_margin_percent,
                result.policy.expected_discount_percent,
                result.policy.rounding_increment,
                result.summary["purchase_account"],
                result.source_columns["purchase_account"],
                result.source_columns["sku"],
                result.source_columns["name"],
                result.source_columns["cost"],
                result.source_columns["price"],
            ],
        }
    )
    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        result.price_list.to_excel(writer, sheet_name="Price List", index=False)
        result.adjustments.to_excel(writer, sheet_name="Low Margin Adjustments", index=False)
        result.blocked.to_excel(writer, sheet_name="Blocked Rows", index=False)
        summary_frame.to_excel(writer, sheet_name="Summary", index=False)
        policy_frame.to_excel(writer, sheet_name="Policy", index=False)
    return destination
