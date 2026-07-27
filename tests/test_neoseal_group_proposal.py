import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "inventory" / "propose_neoseal_groups.py"
SPEC = importlib.util.spec_from_file_location("propose_neoseal_groups", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_build_review_rows_excludes_untracked_and_preserves_current_group():
    rows = MODULE.build_review_rows(
        [
            {
                "item_id": "1",
                "sku": "BIT-4",
                "name": "514 Bitucoat 4kg",
                "group_name": "514 Bitucoat 4kg",
                "group_id": "old-group",
                "purchase_account_id": "purchase",
                "track_inventory": True,
            },
            {
                "item_id": "2",
                "name": "Solvent Rate Difference",
                "track_inventory": False,
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["current_group_name"] == "514 Bitucoat 4kg"
    assert rows[0]["proposed_group_name"] == "Bitucoat"
    assert rows[0]["change_required"] is True
    assert rows[0]["review_action"] == "PENDING"
