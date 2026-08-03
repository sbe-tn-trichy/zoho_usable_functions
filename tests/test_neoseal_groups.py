import pandas as pd
import pytest

from unittest.mock import MagicMock

from zoho_usable_functions.inventory.neoseal_groups import (
    assign_neoseal_group_names,
    post_item_grouping,
)


def test_assigns_product_family_groups_and_sorts_ascending():
    items = pd.DataFrame(
        [
            {"name": "514 Bitucoat 20kg", "group_name": ""},
            {"name": "200 UPVC Solution 100ml Blue (Tin)", "group_name": "old"},
            {"name": '1" UPVC Ball Valve GS', "group_name": None},
            {"name": "514 Bitucoat 4kg", "group_name": "item-specific"},
        ]
    )

    grouped = assign_neoseal_group_names(items)

    assert list(grouped["group_name"]) == [
        "Bitucoat",
        "Bitucoat",
        "UPVC Ball Valve",
        "UPVC Solvent",
    ]


def test_unmatched_item_is_rejected_instead_of_leaving_blank_group():
    items = pd.DataFrame([{"name": "Unknown New Product"}])

    with pytest.raises(ValueError, match="do not cover"):
        assign_neoseal_group_names(items)


def test_assigns_current_neoseal_catalog_variants():
    items = pd.DataFrame(
        [
            {"name": "NEOSEAL 305 CPVC SOLVENT CEMENT - 25ML TUBE"},
            {"name": "NEOSEAL 566 QUICK LEAK STOP - 1KG"},
        ]
    )

    grouped = assign_neoseal_group_names(items)

    assert list(grouped["group_name"]) == ["CPVC Solvent", "Quick Leak Stop"]


def test_assigns_miscellaneous_products_to_neoseal_others():
    items = pd.DataFrame(
        [
            {"name": "753 Gasket Shellac 25g"},
            {"name": "802 Neoflex 20g"},
            {"name": "Drain Cleaner - 50g"},
        ]
    )

    grouped = assign_neoseal_group_names(items)

    assert list(grouped["group_name"]) == [
        "Neoseal Others",
        "Neoseal Others",
        "Neoseal Others",
    ]


def test_item_group_creation_delegates_to_sdk_resource():
    client = MagicMock()
    payload = {"group_name": "Bitucoat", "items": []}
    client.items.group_items.return_value = {"item_group": {"group_id": "123"}}

    result = post_item_grouping(client, payload)

    assert result == {"item_group": {"group_id": "123"}}
    client.items.group_items.assert_called_once_with(payload)
