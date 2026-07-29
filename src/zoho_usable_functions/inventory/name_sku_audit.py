"""Helpers for auditing Zoho item names against their SKUs."""

from __future__ import annotations

import re
from typing import Any, Iterable


def normalize_name_or_sku(value: Any) -> str:
    """Return an uppercase, alphanumeric value suitable for comparison."""
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).strip().upper())


def compare_name_to_sku(name: Any, sku: Any) -> dict[str, Any]:
    """Compare an item name and SKU without discarding their original values."""
    raw_name = "" if name is None else str(name).strip()
    raw_sku = "" if sku is None else str(sku).strip()
    normalized_name = normalize_name_or_sku(raw_name)
    normalized_sku = normalize_name_or_sku(raw_sku)

    exact_match = bool(raw_name and raw_sku and raw_name == raw_sku)
    normalized_match = bool(normalized_name and normalized_sku and normalized_name == normalized_sku)

    if not raw_name:
        result = "missing_name"
    elif not raw_sku:
        result = "missing_sku"
    elif exact_match:
        result = "exact_match"
    elif normalized_match:
        result = "normalized_match"
    elif normalized_sku in normalized_name:
        result = "sku_contained_in_name"
    elif normalized_name in normalized_sku:
        result = "name_contained_in_sku"
    else:
        result = "different"

    return {
        "normalized_name": normalized_name,
        "normalized_sku": normalized_sku,
        "exact_match": exact_match,
        "normalized_match": normalized_match,
        "comparison": result,
    }


def resolve_purchase_account(accounts: Iterable[dict[str, Any]], search_text: str) -> dict[str, Any]:
    """Resolve one purchase account by exact name, then by a unique partial match."""
    needle = search_text.strip().casefold()
    if not needle:
        raise ValueError("purchase account search text cannot be empty")

    account_list = list(accounts)

    def account_name(account: dict[str, Any]) -> str:
        return str(account.get("account_name") or account.get("name") or "").strip()

    exact = [account for account in account_list if account_name(account).casefold() == needle]
    matches = exact or [account for account in account_list if needle in account_name(account).casefold()]

    if not matches:
        from ..core.config import Config
        for name, acct_id in Config.PURCHASE_ACCOUNT_IDS.items():
            if name.casefold() == needle or needle in name.casefold():
                return {"account_id": str(acct_id), "account_name": name}
        raise ValueError(f"No purchase account name contains {search_text!r}")
    if len(matches) > 1:
        names = ", ".join(sorted(account_name(account) for account in matches))
        raise ValueError(f"Multiple purchase accounts match {search_text!r}: {names}")
    return matches[0]
