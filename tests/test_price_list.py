from decimal import Decimal

import pandas as pd
import pytest

from zoho_usable_functions.inventory.price_list import (
    BOOKS_PRICE_LIST_FIELDS,
    PRICE_LIST_CSV_COLUMNS,
    PriceListPolicy,
    generate_price_list,
    write_price_list,
    write_price_list_csv,
)


def test_low_margin_price_is_raised_to_minimum_with_upward_rounding():
    source = pd.DataFrame(
        [{"Purchase Account": "Fans", "SKU": "A-1", "Item Name": "Item A", "Purchase Rate": 80, "Rate": 90}]
    )

    result = generate_price_list(
        source,
        purchase_account="Fans",
        policy=PriceListPolicy(
            minimum_margin_percent=Decimal("20"),
            rounding_increment=Decimal("0.05"),
        ),
    )

    row = result.price_list.iloc[0]
    assert row["Price Status"] == "adjusted_low_margin"
    assert row["Minimum Safe Price"] == 100
    assert row["Proposed Price"] == 100
    assert row["Proposed Margin %"] == pytest.approx(20)
    assert result.summary["adjusted_low_margin"] == 1


def test_expected_discount_is_included_in_margin_protection():
    source = pd.DataFrame(
        [{"Purchase Account": "Fans", "SKU": "A-1", "Item Name": "Item A", "Cost Price": 80, "Selling Price": 100}]
    )

    result = generate_price_list(
        source,
        purchase_account="Fans",
        policy=PriceListPolicy(
            minimum_margin_percent=Decimal("20"),
            expected_discount_percent=Decimal("10"),
            rounding_increment=Decimal("1"),
        ),
    )

    row = result.price_list.iloc[0]
    assert row["Effective Current Price"] == 90
    assert row["Minimum Safe Price"] == 112
    assert row["Proposed Margin %"] >= 20


def test_margin_percentages_are_rounded_to_two_decimal_places():
    source = pd.DataFrame(
        [
            {
                "Purchase Account": "Fans",
                "SKU": "A-1",
                "Item Name": "Item A",
                "Cost Price": 80,
                "Selling Price": 103,
            }
        ]
    )

    row = generate_price_list(source, purchase_account="Fans").price_list.iloc[0]

    assert row["Current Margin %"] == 22.33
    assert row["Proposed Margin %"] == 22.33


def test_compliant_price_is_not_reduced():
    source = pd.DataFrame(
        [{"Purchase Account": "Fans", "SKU": "A-1", "Item Name": "Item A", "Purchase Rate": 50, "Rate": 100}]
    )

    row = generate_price_list(source, purchase_account="Fans").price_list.iloc[0]

    assert row["Price Status"] == "margin_ok"
    assert row["Proposed Price"] == 100
    assert row["Price Adjustment"] == 0


def test_invalid_and_duplicate_rows_are_blocked():
    source = pd.DataFrame(
        [
            {"Purchase Account": "Fans", "SKU": "A-1", "Item Name": "One", "Purchase Rate": 50, "Rate": 100},
            {"Purchase Account": "Fans", "SKU": "a-1", "Item Name": "Two", "Purchase Rate": 50, "Rate": 100},
            {"Purchase Account": "Fans", "SKU": "B-1", "Item Name": "Bad", "Purchase Rate": "unknown", "Rate": 100},
        ]
    )

    result = generate_price_list(source, purchase_account="Fans")

    assert result.summary["blocked"] == 3
    assert "duplicate SKU" in result.blocked.iloc[0]["Validation Issues"]
    assert "invalid or missing cost" in result.blocked.iloc[2]["Validation Issues"]
    assert result.blocked["Proposed Price"].isna().all()


def test_policy_validation():
    with pytest.raises(ValueError, match="below 100"):
        PriceListPolicy(minimum_margin_percent=Decimal("100"))
    with pytest.raises(ValueError, match="greater than 0"):
        PriceListPolicy(rounding_increment=Decimal("0"))


def test_workbook_contains_audit_sheets(tmp_path):
    source = pd.DataFrame(
        [{"Purchase Account": "Fans", "SKU": "A-1", "Item Name": "Item A", "Purchase Rate": 80, "Rate": 90}]
    )
    result = generate_price_list(source, purchase_account="Fans")

    output = write_price_list(result, tmp_path / "prices.xlsx")

    workbook = pd.ExcelFile(output)
    assert workbook.sheet_names == [
        "Price List",
        "Low Margin Adjustments",
        "Blocked Rows",
        "Summary",
        "Policy",
    ]


def test_only_requested_purchase_account_is_analyzed():
    source = pd.DataFrame(
        [
            {"Purchase Account": "Fans", "SKU": "F-1", "Item Name": "Fan", "Purchase Rate": 80, "Rate": 90},
            {"Purchase Account": "Cables", "SKU": "C-1", "Item Name": "Cable", "Purchase Rate": 10, "Rate": 20},
        ]
    )

    result = generate_price_list(source, purchase_account="fans")

    assert list(result.price_list["SKU"]) == ["F-1"]
    assert result.summary["total_rows"] == 1
    assert result.summary["purchase_account"] == "fans"


def test_missing_purchase_account_is_rejected():
    source = pd.DataFrame(
        [{"Purchase Account": "Fans", "SKU": "F-1", "Item Name": "Fan", "Purchase Rate": 80, "Rate": 90}]
    )

    with pytest.raises(ValueError, match="was not found"):
        generate_price_list(source, purchase_account="Cables")


def test_books_output_can_be_restricted_to_required_fields():
    source = pd.DataFrame(
        [
            {
                "purchase_account_name": "Fans",
                "group_name": "Ceiling Fans",
                "item_id": "item-1",
                "sku": "FAN-1",
                "name": "Fan",
                "item_name": "Fan",
                "category_name": "Electrical",
                "unit": "pcs",
                "status": "active",
                "rate": 100,
                "purchase_rate": 80,
                "mrp": 120,
                "unused_api_field": "must not be exported",
            }
        ]
    )

    result = generate_price_list(
        source,
        purchase_account="Fans",
        source_output_columns=BOOKS_PRICE_LIST_FIELDS,
    )

    assert list(result.price_list.columns[: len(BOOKS_PRICE_LIST_FIELDS)]) == list(
        BOOKS_PRICE_LIST_FIELDS
    )
    assert "unused_api_field" not in result.price_list.columns


def test_non_inventory_tracked_items_are_excluded():
    source = pd.DataFrame(
        [
            {
                "Purchase Account": "Neoseal Purchase",
                "SKU": "STOCK-1",
                "Item Name": "Stock Item",
                "Purchase Rate": 80,
                "Rate": 100,
                "track_inventory": True,
            },
            {
                "Purchase Account": "Neoseal Purchase",
                "SKU": "RATE-DIFF",
                "Item Name": "Solvent Rate Difference",
                "Purchase Rate": 0,
                "Rate": 0,
                "track_inventory": False,
            },
        ]
    )

    result = generate_price_list(
        source,
        purchase_account="Neoseal Purchase",
        inventory_tracked_only=True,
    )

    assert list(result.price_list["SKU"]) == ["STOCK-1"]
    assert result.summary["excluded_non_inventory_items"] == 1


def test_csv_contains_exact_import_columns_and_proposed_prices(tmp_path):
    source = pd.DataFrame(
        [
            {
                "purchase_account_name": "Fans",
                "group_name": "Ceiling Fans",
                "item_id": "00123",
                "sku": "FAN-1",
                "name": "Breeze Fan",
                "purchase_rate": 80,
                "rate": 90,
            }
        ]
    )
    result = generate_price_list(
        source,
        purchase_account="Fans",
        policy=PriceListPolicy(minimum_margin_percent=Decimal("20")),
    )

    output = write_price_list_csv(result, tmp_path / "prices.csv")
    exported = pd.read_csv(output, dtype={"ItemId": str, "SKU": str})

    assert list(exported.columns) == list(PRICE_LIST_CSV_COLUMNS)
    assert exported.iloc[0].to_dict() == {
        "Group Name": "Ceiling Fans",
        "Item Name": "Breeze Fan",
        "SKU": "FAN-1",
        "Cost Price": 80,
        "Sales Price": 100.0,
        "Margin": 20.0,
        "ItemId": "00123",
    }


def test_csv_excludes_blocked_rows(tmp_path):
    source = pd.DataFrame(
        [
            {
                "purchase_account_name": "Fans",
                "group_name": "Ceiling Fans",
                "item_id": "item-1",
                "sku": "FAN-1",
                "name": "Valid Fan",
                "purchase_rate": 80,
                "rate": 100,
            },
            {
                "purchase_account_name": "Fans",
                "group_name": "Ceiling Fans",
                "item_id": "item-2",
                "sku": "FAN-2",
                "name": "Invalid Fan",
                "purchase_rate": 80,
                "rate": 0,
            },
        ]
    )
    result = generate_price_list(source, purchase_account="Fans")

    output = write_price_list_csv(result, tmp_path / "prices.csv")
    exported = pd.read_csv(output)

    assert list(exported["SKU"]) == ["FAN-1"]


def test_csv_requires_group_and_item_id_fields(tmp_path):
    source = pd.DataFrame(
        [
            {
                "Purchase Account": "Fans",
                "SKU": "FAN-1",
                "Item Name": "Fan",
                "Purchase Rate": 80,
                "Rate": 100,
            }
        ]
    )
    result = generate_price_list(source, purchase_account="Fans")

    with pytest.raises(ValueError, match="Group Name is unavailable"):
        write_price_list_csv(result, tmp_path / "prices.csv")
