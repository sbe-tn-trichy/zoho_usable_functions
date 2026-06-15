"""
reconciliation.matcher
~~~~~~~~~~~~~~~~~~~~~~
Public re-export facade.

All reconciliation logic lives in the private sub-modules:
  ._utils            — primitive date / amount / ref helpers
  ._bank_matcher     — bank-statement ↔ Zoho Books matching
  ._vendor_reconciler — vendor-account 4-way reconciliation

Import from this module as usual — nothing external changes.
"""
from ..core.models import DotDict
from ._utils import parse_date, get_abs_amount, ref_match
from ._bank_matcher import match_ledger_entries as _match_ledger_entries
from ._bank_matcher import match_bank_with_vendor_ledger as _match_bank_with_vendor_ledger
from ._vendor_reconciler import (
    fetch_vendor_credits,
    check_credit_ref,
    check_bill_ref,
    check_payment_ref,
    reconcile_document_group,
    reconcile_vendor_account as _reconcile_vendor_account,
    reconcile_vendor as _reconcile_vendor,
)

def match_ledger_entries(*args, **kwargs) -> DotDict:
    return DotDict(_match_ledger_entries(*args, **kwargs))

def match_bank_with_vendor_ledger(*args, **kwargs) -> DotDict:
    return DotDict(_match_bank_with_vendor_ledger(*args, **kwargs))

def reconcile_vendor_account(*args, **kwargs) -> DotDict:
    return DotDict(_reconcile_vendor_account(*args, **kwargs))

def reconcile_vendor(*args, **kwargs) -> DotDict:
    return DotDict(_reconcile_vendor(*args, **kwargs))

__all__ = [
    "parse_date",
    "get_abs_amount",
    "ref_match",
    "match_ledger_entries",
    "match_bank_with_vendor_ledger",
    "fetch_vendor_credits",
    "check_credit_ref",
    "check_bill_ref",
    "check_payment_ref",
    "reconcile_document_group",
    "reconcile_vendor_account",
    "reconcile_vendor",
]
