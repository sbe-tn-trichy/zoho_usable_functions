import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "inventory" / "generate_price_list.py"
)
SPEC = importlib.util.spec_from_file_location("generate_price_list_script", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_fetch_purchase_account_items_requests_only_active_items(monkeypatch):
    client = MagicMock()
    client.items.list_by_purchase_account.return_value = [
        {"item_id": "item-1", "name": "Active item"}
    ]
    monkeypatch.setattr(MODULE, "get_books_client", lambda: client)

    result = MODULE.fetch_purchase_account_items("Neoseal Purchase", "account-1")

    client.items.list_by_purchase_account.assert_called_once_with(
        "account-1", status="active"
    )
    assert result.iloc[0]["purchase_account_name"] == "Neoseal Purchase"
    assert result.iloc[0]["purchase_account_id"] == "account-1"
