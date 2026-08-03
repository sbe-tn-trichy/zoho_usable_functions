"""Boundary tests proving promoted workflows are owned by zoho-sdk."""

import importlib

import workflows.polycab_credit_memos.processor as sdk_credit_memos
import workflows.vendor_ledger_reconciliation.cleaner as sdk_cleaner
import workflows.vendor_ledger_reconciliation.zeiss_pdf as sdk_zeiss_pdf

from zoho_usable_functions import DotDict, parse_polycab_credit_memo
from zoho_usable_functions.reconciliation.cleaner import clean_ledger_file
from zoho_usable_functions.reconciliation.zeiss_pdf import parse_zeiss_pdf_statement


def test_promoted_public_objects_come_from_sdk():
    assert parse_polycab_credit_memo is sdk_credit_memos.parse_polycab_credit_memo
    assert clean_ledger_file is sdk_cleaner.clean_ledger_file
    assert parse_zeiss_pdf_statement is sdk_zeiss_pdf.parse_zeiss_pdf_statement
    assert DotDict.__module__ == "workflows.core.models"


def test_legacy_processor_module_is_sdk_module_alias():
    legacy = importlib.import_module(
        "zoho_usable_functions.credit_memos.processor"
    )
    assert legacy is sdk_credit_memos
