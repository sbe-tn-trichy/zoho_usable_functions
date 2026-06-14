import unittest
from unittest.mock import MagicMock
from datetime import date
from zoho_usable_functions.reconciliation.matcher import (
    parse_date,
    get_abs_amount,
    ref_match,
    match_ledger_entries
)

class TestLedgerMatcherUtils(unittest.TestCase):
    def test_parse_date(self):
        self.assertEqual(parse_date("2026-06-14"), date(2026, 6, 14))
        self.assertEqual(parse_date("2026-06-14T11:24:20Z"), date(2026, 6, 14))
        self.assertEqual(parse_date(date(2026, 6, 14)), date(2026, 6, 14))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("invalid-date"))

    def test_get_abs_amount(self):
        self.assertEqual(get_abs_amount({"amount": "-150.50"}), 150.50)
        self.assertEqual(get_abs_amount({"amount": 150.50}), 150.50)
        self.assertEqual(get_abs_amount({"amount": "abc"}), 0.0)

    def test_ref_match(self):
        self.assertTrue(ref_match("REF123", "  ref123  "))
        self.assertFalse(ref_match("REF123", ""))
        self.assertFalse(ref_match("", ""))
        self.assertFalse(ref_match("REF123", "REF456"))

class TestMatchLedgerEntries(unittest.TestCase):
    def setUp(self):
        self.books_client = MagicMock()
        self.bank_account_id = "bank_123"
        self.vendor_id = "vendor_456"

    def test_match_ledger_entries(self):
        # Setup mock bank transactions (withdrawals/debits)
        bank_transactions = [
            # Exact Match 1
            {
                "transaction_id": "tx_01",
                "date": "2026-06-10",
                "amount": "-1000.00",
                "reference_number": "REF-001",
                "debit_or_credit": "debit"
            },
            # Strong Match 2 (no ref match, but exact amount and within date tolerance)
            {
                "transaction_id": "tx_02",
                "date": "2026-06-11",
                "amount": "-500.00",
                "reference_number": "REF-002",
                "debit_or_credit": "debit"
            },
            # Weak Match 3 (amount off by 5.0, but within tolerance of 10.0, and within date tolerance)
            {
                "transaction_id": "tx_03",
                "date": "2026-06-12",
                "amount": "-255.00",
                "reference_number": "REF-003",
                "debit_or_credit": "debit"
            },
            # Unmatched Bank Transaction
            {
                "transaction_id": "tx_04",
                "date": "2026-06-13",
                "amount": "-1500.00",
                "reference_number": "REF-004",
                "debit_or_credit": "debit"
            },
            # Deposit (should be ignored because it is not a withdrawal/outflow)
            {
                "transaction_id": "tx_05",
                "date": "2026-06-10",
                "amount": "1000.00",
                "debit_or_credit": "credit"
            }
        ]

        # Setup mock vendor payments
        vendor_payments = [
            # Exact Match with tx_01
            {
                "payment_id": "vp_01",
                "date": "2026-06-10",
                "amount": "1000.00",
                "reference_number": "REF-001"
            },
            # Strong Match with tx_02 (different ref)
            {
                "payment_id": "vp_02",
                "date": "2026-06-12",
                "amount": "500.00",
                "reference_number": "REF-ABC"
            },
            # Weak Match with tx_03 (amount is 250.00, difference of 5.00)
            {
                "payment_id": "vp_03",
                "date": "2026-06-11",
                "amount": "250.00",
                "reference_number": "REF-003"
            },
            # Unmatched Vendor Payment
            {
                "payment_id": "vp_04",
                "date": "2026-06-10",
                "amount": "75.00",
                "reference_number": "REF-009"
            }
        ]

        self.books_client.bank_transactions.list_all.return_value = bank_transactions
        self.books_client.vendor_payments.list_all.return_value = vendor_payments

        # Match with 10.0 amount tolerance, 7 days date tolerance
        results = match_ledger_entries(
            books_client=self.books_client,
            bank_account_id=self.bank_account_id,
            vendor_id=self.vendor_id,
            date_tolerance_days=7,
            amount_tolerance=10.0
        )

        self.books_client.bank_transactions.list_all.assert_called_once_with(params={"account_id": self.bank_account_id})
        self.books_client.vendor_payments.list_all.assert_called_once_with(params={"vendor_id": self.vendor_id})

        # Verify exact matches
        self.assertEqual(len(results["exact_matches"]), 1)
        self.assertEqual(results["exact_matches"][0][0]["transaction_id"], "tx_01")
        self.assertEqual(results["exact_matches"][0][1]["payment_id"], "vp_01")

        # Verify strong matches
        self.assertEqual(len(results["strong_matches"]), 1)
        self.assertEqual(results["strong_matches"][0][0]["transaction_id"], "tx_02")
        self.assertEqual(results["strong_matches"][0][1]["payment_id"], "vp_02")

        # Verify weak matches
        self.assertEqual(len(results["weak_matches"]), 1)
        self.assertEqual(results["weak_matches"][0][0]["transaction_id"], "tx_03")
        self.assertEqual(results["weak_matches"][0][1]["payment_id"], "vp_03")

        # Verify unmatched bank transactions (tx_04 remains, deposit tx_05 is excluded entirely)
        self.assertEqual(len(results["unmatched_bank_transactions"]), 1)
        self.assertEqual(results["unmatched_bank_transactions"][0]["transaction_id"], "tx_04")

        # Verify unmatched vendor payments (vp_04 remains)
        self.assertEqual(len(results["unmatched_vendor_payments"]), 1)
        self.assertEqual(results["unmatched_vendor_payments"][0]["payment_id"], "vp_04")

from unittest.mock import patch
from zoho_usable_functions.reconciliation.matcher import match_bank_with_vendor_ledger, reconcile_vendor_account

class TestMatchBankWithVendorLedger(unittest.TestCase):
    def setUp(self):
        self.books_client = MagicMock()
        self.bank_account_id = "bank_123"
        self.ledger_path = "dummy_ledger.xls"

    @patch("os.path.exists")
    @patch("zoho_usable_functions.reconciliation.matcher.clean_ledger_file")
    def test_match_bank_with_vendor_ledger(self, mock_clean, mock_exists):
        mock_exists.return_value = True
        
        # Setup mock bank transactions (withdrawals)
        bank_transactions = [
            {
                "transaction_id": "tx_01",
                "date": "2026-01-02",
                "amount": "-314189.27",
                "reference_number": "TN721S2526104838",
                "debit_or_credit": "debit"
            },
            {
                "transaction_id": "tx_02",
                "date": "2026-01-03",
                "amount": "-541000.00",
                "cheque_number": "NBJ4RH6RTKHVQZTP",
                "debit_or_credit": "debit"
            }
        ]
        self.books_client.bank_transactions.list_all.return_value = bank_transactions
        
        # Setup mock cleaned ledger entries
        mock_clean.return_value = [
            # Receipt (Credit) -> Matches tx_02 exactly by ref (transaction_no is check ref) and amount and date
            {
                "account_no": "108738",
                "account_name": "LTG-BHARATH DISTRIBUTORS",
                "date": "2026-01-03",
                "document_type": "Receipt",
                "transaction_no": "NBJ4RH6RTKHVQZTP",
                "transaction_reference": "",
                "debit_amount": 0.0,
                "credit_amount": 541000.0,
                "closing_balance": -109972.46
            },
            # Sales Invoice -> Ignored since debit_amount > 0 and credit_amount == 0 and not Receipt
            {
                "account_no": "109461",
                "account_name": "FAN-BHARATH DISTRIBUTORS",
                "date": "2026-01-02",
                "document_type": "Sales Invoice",
                "transaction_no": "2601238365",
                "transaction_reference": "TN721S2526104838",
                "debit_amount": 314189.27,
                "credit_amount": 0.0,
                "closing_balance": -40884.44
            }
        ]
        
        results = match_bank_with_vendor_ledger(
            books_client=self.books_client,
            bank_account_id=self.bank_account_id,
            vendor_ledger_path=self.ledger_path,
            date_tolerance_days=7,
            amount_tolerance=0.0
        )
        
        self.books_client.bank_transactions.list_all.assert_called_once_with(params={"account_id": self.bank_account_id})
        mock_clean.assert_called_once_with(self.ledger_path)
        
        # tx_02 matches the ledger Receipt
        self.assertEqual(len(results["exact_matches"]), 1)
        self.assertEqual(results["exact_matches"][0][0]["transaction_id"], "tx_02")
        self.assertEqual(results["exact_matches"][0][1]["transaction_no"], "NBJ4RH6RTKHVQZTP")
        
        # tx_01 has no matching credit receipt in Polycab's ledger (only a sales invoice, which we skip)
        self.assertEqual(len(results["unmatched_bank_transactions"]), 1)
        self.assertEqual(results["unmatched_bank_transactions"][0]["transaction_id"], "tx_01")
        
        # No unmatched ledger receipts since the only one got matched
        self.assertEqual(len(results["unmatched_ledger_receipts"]), 0)


class TestReconcileVendorAccount(unittest.TestCase):
    def setUp(self):
        self.books_client = MagicMock()
        self.vendor_id = "vendor_123"
        self.ledger_path = "dummy_ledger.xls"

    @patch("os.path.exists")
    @patch("zoho_usable_functions.reconciliation.matcher.get_ledger_metadata")
    @patch("zoho_usable_functions.reconciliation.matcher.clean_ledger_file")
    def test_reconcile_vendor_account(self, mock_clean, mock_metadata, mock_exists):
        mock_exists.return_value = True
        mock_metadata.return_value = {
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "party_name": "POLYCAB INDIA LIMITED",
            "opening_balance": 0.0
        }
        
        # Mock cleaned ledger entries (1 sales invoice, 1 receipt, 1 credit memo, 1 debit memo)
        mock_clean.return_value = [
            {
                "account_no": "109461",
                "account_name": "FAN-BHARATH DISTRIBUTORS",
                "date": "2026-01-02",
                "document_type": "Sales Invoice",
                "transaction_no": "2601238365",
                "transaction_reference": "TN721S2526104838",
                "debit_amount": 314189.27,
                "credit_amount": 0.0,
                "closing_balance": -40884.44
            },
            {
                "account_no": "108738",
                "account_name": "LTG-BHARATH DISTRIBUTORS",
                "date": "2026-01-03",
                "document_type": "Receipt",
                "transaction_no": "NBJ4RH6RTKHVQZTP",
                "transaction_reference": "",
                "debit_amount": 0.0,
                "credit_amount": 541000.0,
                "closing_balance": -109972.46
            },
            {
                "account_no": "108738",
                "account_name": "LTG-BHARATH DISTRIBUTORS",
                "date": "2026-01-04",
                "document_type": "Credit Memo",
                "transaction_no": "VC-111",
                "transaction_reference": "",
                "debit_amount": 0.0,
                "credit_amount": 100.0,
                "closing_balance": -110072.46
            },
            {
                "account_no": "108738",
                "account_name": "LTG-BHARATH DISTRIBUTORS",
                "date": "2026-01-05",
                "document_type": "Debit Memo",
                "transaction_no": "DB-111",
                "transaction_reference": "",
                "debit_amount": 50.0,
                "credit_amount": 0.0,
                "closing_balance": -110022.46
            }
        ]
        
        # Mock Zoho Bills (1 matching bill, 1 unmatched bill, 1 negative bill for debit memo)
        zoho_bills = [
            {
                "bill_id": "bill_01",
                "date": "2026-01-02",
                "bill_number": "2601238365",
                "reference_number": "",
                "amount": "314189.27",
                "total": "314189.27"
            },
            {
                "bill_id": "bill_02",
                "date": "2026-01-15",
                "bill_number": "BILL-999",
                "reference_number": "",
                "amount": "12345.00",
                "total": "12345.00"
            },
            {
                "bill_id": "bill_03",
                "date": "2026-01-05",
                "bill_number": "DB-111",
                "reference_number": "",
                "amount": "-50.00",
                "total": "-50.00"
            }
        ]
        self.books_client.bills.list_all.return_value = zoho_bills
        
        # Mock Zoho Vendor Payments (1 matching payment, 1 unmatched payment)
        zoho_payments = [
            {
                "payment_id": "pay_01",
                "date": "2026-01-03",
                "amount": "541000.00",
                "reference_number": "NBJ4RH6RTKHVQZTP"
            },
            {
                "payment_id": "pay_02",
                "date": "2026-01-20",
                "amount": "9999.00",
                "reference_number": "REF-999"
            }
        ]
        self.books_client.vendor_payments.list_all.return_value = zoho_payments
        
        # Mock vendorcredits API call
        def mock_request(method, endpoint, params=None):
            if endpoint == 'vendorcredits':
                return {
                    "vendorcredits": [
                        {
                            "vendor_credit_id": "vc_01",
                            "date": "2026-01-04",
                            "vendor_credit_number": "VC-111",
                            "total": "100.00"
                        }
                    ],
                    "page_context": {"has_more_page": False}
                }
            return {}
        self.books_client.request = mock_request
        
        results = reconcile_vendor_account(
            books_client=self.books_client,
            vendor_id=self.vendor_id,
            vendor_ledger_path=self.ledger_path,
            date_tolerance_days=7,
            amount_tolerance=0.0
        )
        
        # Verify calls
        mock_clean.assert_called_once_with(self.ledger_path)
        self.books_client.bills.list_all.assert_called_once_with(params={"vendor_id": self.vendor_id, "from_date": "2026-01-01", "to_date": "2026-03-31"})
        self.books_client.vendor_payments.list_all.assert_called_once_with(params={"vendor_id": self.vendor_id, "from_date": "2026-01-01", "to_date": "2026-03-31"})
        
        # Verify Sales Invoice matches/unmatched
        sales_inv = results["sales_invoice"]
        self.assertEqual(len(sales_inv["matches"]), 1)
        self.assertEqual(sales_inv["matches"][0][0]["bill_id"], "bill_01")
        self.assertEqual(sales_inv["matches"][0][1]["transaction_no"], "2601238365")
        self.assertEqual(len(sales_inv["unmatched_books"]), 1)
        self.assertEqual(sales_inv["unmatched_books"][0]["bill_id"], "bill_02")
        self.assertEqual(len(sales_inv["unmatched_ledger"]), 0)
        
        # Verify Receipt matches/unmatched
        receipt = results["receipt"]
        self.assertEqual(len(receipt["matches"]), 1)
        self.assertEqual(receipt["matches"][0][0]["payment_id"], "pay_01")
        self.assertEqual(receipt["matches"][0][1]["transaction_no"], "NBJ4RH6RTKHVQZTP")
        self.assertEqual(len(receipt["unmatched_books"]), 1)
        self.assertEqual(receipt["unmatched_books"][0]["payment_id"], "pay_02")
        self.assertEqual(len(receipt["unmatched_ledger"]), 0)

        # Verify Credit Memo matches/unmatched
        credit_memo = results["credit_memo"]
        self.assertEqual(len(credit_memo["matches"]), 1)
        self.assertEqual(credit_memo["matches"][0][0]["vendor_credit_id"], "vc_01")
        self.assertEqual(credit_memo["matches"][0][1]["transaction_no"], "VC-111")
        self.assertEqual(len(credit_memo["unmatched_books"]), 0)
        self.assertEqual(len(credit_memo["unmatched_ledger"]), 0)

        # Verify Debit Memo matches/unmatched
        debit_memo = results["debit_memo"]
        self.assertEqual(len(debit_memo["matches"]), 1)
        self.assertEqual(debit_memo["matches"][0][0]["bill_id"], "bill_03")
        self.assertEqual(debit_memo["matches"][0][1]["transaction_no"], "DB-111")
        self.assertEqual(len(debit_memo["unmatched_books"]), 0)
        self.assertEqual(len(debit_memo["unmatched_ledger"]), 0)



