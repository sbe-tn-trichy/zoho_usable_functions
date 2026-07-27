import pytest

from zoho_usable_functions.inventory.name_sku_audit import compare_name_to_sku, resolve_purchase_account


@pytest.mark.parametrize(
    ("name", "sku", "expected"),
    [
        ("NS-100", "NS-100", "exact_match"),
        ("NS 100", "ns-100", "normalized_match"),
        ("Neoseal NS-100", "NS100", "sku_contained_in_name"),
        ("NS-100", "", "missing_sku"),
        ("", "NS-100", "missing_name"),
        ("Sealant", "NS-100", "different"),
    ],
)
def test_compare_name_to_sku(name, sku, expected):
    result = compare_name_to_sku(name, sku)

    assert result["comparison"] == expected


def test_resolve_purchase_account_prefers_exact_match():
    accounts = [
        {"account_id": "1", "account_name": "Neoseal"},
        {"account_id": "2", "account_name": "Neoseal Purchase"},
    ]

    assert resolve_purchase_account(accounts, "neoseal")["account_id"] == "1"


def test_resolve_purchase_account_rejects_ambiguous_partial_match():
    accounts = [
        {"account_id": "1", "account_name": "Neoseal Purchase"},
        {"account_id": "2", "account_name": "Neoseal Purchase Returns"},
    ]

    with pytest.raises(ValueError, match="Multiple purchase accounts"):
        resolve_purchase_account(accounts, "neoseal")
