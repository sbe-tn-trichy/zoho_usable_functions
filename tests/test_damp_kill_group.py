import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "inventory"
    / "neoseal"
    / "group_damp_kill.py"
)
SPEC = importlib.util.spec_from_file_location("group_damp_kill", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_build_grouping_payload_uses_normalized_size_variants():
    details = [
        {
            "unit": "NOS",
            "purchase_account_id": "purchase",
            "account_id": "sales",
            "inventory_account_id": "inventory",
        }
        for _ in MODULE.VARIANTS
    ]

    payload = MODULE.build_grouping_payload(details)

    assert payload["group_name"] == "Damp Kill"
    assert payload["attribute_name1"] == "Size"
    assert [item["attribute_option_name1"] for item in payload["items"]] == [
        "10 L",
        "20 L",
    ]
    assert [item["sku"] for item in payload["items"]] == [
        "507-10-L",
        "507-20-L",
    ]
