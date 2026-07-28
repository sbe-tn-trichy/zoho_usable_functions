import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "inventory"
    / "neoseal"
    / "apply_remaining_changes.py"
)
SPEC = importlib.util.spec_from_file_location("apply_remaining_changes", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_reviewed_manifest_has_unique_target_skus_and_expected_groups():
    desired_skus = list(MODULE.CORRECTIONS.values())
    desired_skus = [change["sku"] for change in desired_skus if "sku" in change]

    assert len(desired_skus) == len({sku.casefold() for sku in desired_skus})
    assert MODULE.CORRECTIONS["1094368000038032568"]["sku"] == "753-25"
    assert "Neoseal Others" in MODULE.NEW_GROUPS
    assert "UPVC Solvent" in MODULE.SOLVENT_ADDITIONS
    assert "CPVC Solvent" in MODULE.SOLVENT_ADDITIONS


def test_new_group_payload_preserves_reviewed_name_and_sku_changes():
    item_id = "1094368000038032568"
    details = {
        item_id: {
            "name": "753 Gasket Shellac 25g",
            "sku": "shellac",
            "unit": "NOS",
            "purchase_account_id": "purchase",
            "account_id": "sales",
            "inventory_account_id": "inventory",
        }
    }

    payload = MODULE._new_group_payload(
        "Neoseal Others", "Product", {item_id: "Gasket Shellac"}, details
    )

    assert payload["items"][0]["sku"] == "753-25"
