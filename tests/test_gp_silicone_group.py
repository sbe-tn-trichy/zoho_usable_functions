import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "inventory"
    / "neoseal"
    / "group_gp_silicone_sealant.py"
)
SPEC = importlib.util.spec_from_file_location("group_gp_silicone_sealant", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_build_grouping_payload_uses_correct_names_and_color_variants():
    details = [
        {
            "unit": "pcs",
            "purchase_account_id": "purchase",
            "account_id": "sales",
            "inventory_account_id": "inventory",
            "category_id": "category",
        }
        for _ in MODULE.VARIANTS
    ]

    payload = MODULE.build_grouping_payload(details)

    assert payload["group_name"] == "GP Silicone Sealant"
    assert payload["attribute_name1"] == "Color"
    assert [item["attribute_option_name1"] for item in payload["items"]] == [
        "Black",
        "Clear",
        "White",
    ]
    assert [item["sku"] for item in payload["items"]] == [
        "701-260-B",
        "701-260-C",
        "701-260-W",
    ]
