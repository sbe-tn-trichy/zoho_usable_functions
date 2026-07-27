import pandas as pd
import pytest

from zoho_usable_functions.inventory.neoseal_groups import assign_neoseal_group_names


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
