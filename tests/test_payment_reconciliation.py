import csv
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from zoho_usable_functions.payment_reconciliation.matcher import (
    PaymentReconciliationConfig,
    PaymentReconciliationResult,
    analytics_search_matches_for_bank_line,
    confirm_payment_matches,
    fetch_payment_reconciliation_data,
    fetch_unmatched_bank_statement_lines,
    find_exact_payment_matches,
    fetch_bank_statement_lines,
    is_deposit_books_bank_transaction,
    normalize_bank_statement_line,
    normalize_creator_payment,
    reference_date_amount_match_rows,
    write_creator_payments_csv,
    write_payment_reconciliation_csv,
    write_reference_date_amount_matches_csv,
    write_unmatched_bank_statement_csv,
)
from zoho_usable_functions.payment_reconciliation.models import (
    AnalyticsCustomer,
    BankStatementLine,
    CreatorPayment,
    PaymentMatch,
)


def test_find_exact_payment_matches_requires_unique_100_percent_match():
    creator_payments = [
        CreatorPayment(
            id="pay_1",
            date=date(2026, 6, 20),
            amount=12500.0,
            customer_id="cust_1",
            reference="UTR123",
        ),
        CreatorPayment(
            id="pay_2",
            date=date(2026, 6, 20),
            amount=500.0,
            customer_id="cust_2",
            reference="UTR999",
        ),
    ]
    bank_lines = [
        BankStatementLine(
            id="bank_1",
            date=date(2026, 6, 20),
            amount=12500.0,
            reference="UTR123",
            description="NEFT UTR123",
        ),
        BankStatementLine(
            id="bank_2",
            date=date(2026, 6, 20),
            amount=500.0,
            reference="NOPE",
            description="unknown",
        ),
    ]
    analytics_rows = [
        AnalyticsCustomer(customer_id="cust_1", bank_transaction_id="bank_1", reference="UTR123"),
        AnalyticsCustomer(customer_id="cust_2", bank_transaction_id="bank_2", reference="OTHER"),
    ]

    matches, ambiguous, unmatched_creator, unmatched_bank = find_exact_payment_matches(
        creator_payments,
        bank_lines,
        analytics_rows,
    )

    assert len(matches) == 1
    assert matches[0].creator_payment.id == "pay_1"
    assert matches[0].bank_statement_line.id == "bank_1"
    assert ambiguous == []
    assert [payment.id for payment in unmatched_creator] == ["pay_2"]
    assert [line.id for line in unmatched_bank] == ["bank_2"]


def test_find_exact_payment_matches_reads_reference_from_bank_description():
    creator_payments = [
        CreatorPayment(
            id="pay_1",
            date=date(2026, 6, 20),
            amount=12500.0,
            customer_id="cust_1",
            reference="UTR123456",
        ),
    ]
    bank_lines = [
        BankStatementLine(
            id="bank_1",
            date=date(2026, 6, 20),
            amount=12500.0,
            description="NEFT/UTR123456/customer payment",
        ),
    ]
    analytics_rows = [
        AnalyticsCustomer(
            customer_id="cust_1",
            bank_transaction_id="bank_1",
            search_key="NEFT/UTR123456/customer payment",
        ),
    ]

    matches, ambiguous, unmatched_creator, unmatched_bank = find_exact_payment_matches(
        creator_payments,
        bank_lines,
        analytics_rows,
    )

    assert [match.creator_payment.id for match in matches] == ["pay_1"]
    assert ambiguous == []
    assert unmatched_creator == []
    assert unmatched_bank == []


def test_find_exact_payment_matches_flags_ambiguous_duplicates():
    creator_payments = [
        CreatorPayment(id="pay_1", date=date(2026, 6, 20), amount=100.0, customer_id="cust_1", reference="UTR123"),
        CreatorPayment(id="pay_2", date=date(2026, 6, 20), amount=100.0, customer_id="cust_1", reference="UTR123"),
    ]
    bank_lines = [
        BankStatementLine(id="bank_1", date=date(2026, 6, 20), amount=100.0, reference="UTR123"),
    ]
    analytics_rows = [
        AnalyticsCustomer(customer_id="cust_1", bank_transaction_id="bank_1", reference="UTR123"),
    ]

    matches, ambiguous, unmatched_creator, unmatched_bank = find_exact_payment_matches(
        creator_payments,
        bank_lines,
        analytics_rows,
    )

    assert matches == []
    assert len(ambiguous) == 1
    assert len(unmatched_creator) == 2
    assert len(unmatched_bank) == 1


def test_find_exact_payment_matches_rejects_one_payment_for_two_bank_lines():
    creator_payments = [
        CreatorPayment(
            id="pay_1",
            date=date(2026, 6, 20),
            amount=100.0,
            customer_id="cust_1",
            reference="UTR123",
        ),
    ]
    bank_lines = [
        BankStatementLine(id="bank_1", date=date(2026, 6, 20), amount=100.0, reference="UTR123"),
        BankStatementLine(id="bank_2", date=date(2026, 6, 20), amount=100.0, reference="UTR123"),
    ]
    analytics_rows = [
        AnalyticsCustomer(customer_id="cust_1", bank_transaction_id="bank_1", reference="UTR123"),
        AnalyticsCustomer(customer_id="cust_1", bank_transaction_id="bank_2", reference="UTR123"),
    ]

    matches, ambiguous, unmatched_creator, unmatched_bank = find_exact_payment_matches(
        creator_payments,
        bank_lines,
        analytics_rows,
    )

    assert matches == []
    assert len(ambiguous) == 2
    assert [item["reason"] for item in ambiguous] == [
        "creator payment also matches another bank statement line",
        "creator payment also matches another bank statement line",
    ]
    assert unmatched_creator == creator_payments
    assert unmatched_bank == bank_lines


def test_confirm_payment_matches_is_dry_run_by_default():
    books_client = MagicMock()
    match = MagicMock()
    match.creator_payment.id = "pay_1"
    match.creator_payment.amount = 100.0
    match.bank_statement_line.id = "bank_1"

    confirmed, responses = confirm_payment_matches(books_client, [match])

    assert confirmed == []
    assert responses[0]["dry_run"] is True
    books_client.bank_transactions.match.assert_not_called()


def test_confirm_payment_matches_calls_books_when_enabled():
    books_client = MagicMock()
    books_client.bank_transactions.match.return_value = {"code": 0}
    match = MagicMock()
    match.creator_payment.id = "pay_1"
    match.creator_payment.amount = 100.0
    match.bank_statement_line.id = "bank_1"

    confirmed, responses = confirm_payment_matches(books_client, [match], dry_run=False)

    assert confirmed == [match]
    assert responses == [{"code": 0}]
    books_client.bank_transactions.match.assert_called_once_with(
        "bank_1",
        {
            "transactions": [
                {
                    "transaction_id": "pay_1",
                    "transaction_type": "customer_payment",
                    "amount": 100.0,
                }
            ]
        },
    )


def test_confirm_payment_matches_does_not_confirm_rejected_books_response():
    books_client = MagicMock()
    books_client.bank_transactions.match.return_value = {
        "code": 1002,
        "message": "The transaction could not be matched",
    }
    match = MagicMock()
    match.creator_payment.id = "pay_1"
    match.creator_payment.amount = 100.0
    match.bank_statement_line.id = "bank_1"

    confirmed, responses = confirm_payment_matches(books_client, [match], dry_run=False)

    assert confirmed == []
    assert responses == [{"code": 1002, "message": "The transaction could not be matched"}]


def test_normalizers_convert_datetime_values_to_dates():
    timestamp = datetime(2026, 6, 20, 14, 30)

    creator = normalize_creator_payment({"ID": "pay_1", "Payment_Date": timestamp})
    bank_line = normalize_bank_statement_line({"transaction_id": "bank_1", "date": timestamp})

    assert creator.date == date(2026, 6, 20)
    assert type(creator.date) is date
    assert bank_line.date == date(2026, 6, 20)
    assert type(bank_line.date) is date


@patch("zoho_usable_functions.payment_reconciliation.matcher.fetch_analytics_customer_table")
@patch("zoho_usable_functions.payment_reconciliation.matcher.fetch_unmatched_bank_statement_lines")
@patch("zoho_usable_functions.payment_reconciliation.matcher.fetch_creator_payments")
def test_fetch_reconciliation_data_only_uses_unmatched_bank_lines(
    mock_fetch_creator,
    mock_fetch_unmatched,
    mock_fetch_analytics,
):
    mock_fetch_creator.return_value = ["creator"]
    mock_fetch_unmatched.return_value = ["bank"]
    mock_fetch_analytics.return_value = ["analytics"]
    creator_client = MagicMock()
    books_client = MagicMock()
    config = PaymentReconciliationConfig()

    result = fetch_payment_reconciliation_data(creator_client, books_client, "token", config)

    assert result == (["creator"], ["bank"], ["analytics"])
    mock_fetch_unmatched.assert_called_once_with(books_client, config)


def test_write_payment_reconciliation_csv(tmp_path):
    match = PaymentMatch(
        creator_payment=CreatorPayment(
            id="pay_1",
            date=date(2026, 6, 20),
            amount=12500.0,
            customer_id="cust_1",
            customer_name="Bharath",
            reference="UTR123",
        ),
        bank_statement_line=BankStatementLine(
            id="bank_1",
            date=date(2026, 6, 20),
            amount=12500.0,
            reference="UTR123",
            description="NEFT UTR123",
            bank_account_id="bank_acct_1",
        ),
        analytics_customer=AnalyticsCustomer(
            customer_id="cust_1",
            bank_transaction_id="bank_1",
            reference="UTR123",
            search_key="NEFT UTR123",
            customer_name="Bharath",
        ),
    )
    result = PaymentReconciliationResult(
        exact_matches=[match],
        confirmed_matches=[],
        confirmation_responses=[],
        ambiguous_matches=[],
        unmatched_creator_payments=[
            CreatorPayment(id="pay_2", date=date(2026, 6, 21), amount=500.0, customer_id="cust_2")
        ],
        unmatched_bank_statement_lines=[
            BankStatementLine(id="bank_2", date=date(2026, 6, 22), amount=750.0)
        ],
    )

    output_path = tmp_path / "payment_reconciliation.csv"

    written_path = write_payment_reconciliation_csv(result, str(output_path))

    assert written_path == str(output_path)
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["status"] for row in rows] == [
        "exact_match",
        "unmatched_creator_payment",
        "unmatched_bank_statement_line",
    ]
    assert rows[0]["creator_payment_id"] == "pay_1"
    assert rows[0]["bank_transaction_id"] == "bank_1"


def test_fetch_unmatched_bank_statement_lines_uses_books_uncategorized_filter():
    books_client = MagicMock()
    books_client.bank_transactions.list_all.return_value = [
        {
            "transaction_id": "bank_1",
            "date": "2026-06-20",
            "amount": 100.0,
            "description": "UPI rjshgomathi-1@o",
            "status": "uncategorized",
        }
    ]
    config = PaymentReconciliationConfig(
        bank_account_ids=("acct_1",),
        bank_account_names={"acct_1": "IDFC"},
    )

    rows = fetch_unmatched_bank_statement_lines(books_client, config)

    assert len(rows) == 1
    assert rows[0].bank_name == "IDFC"
    books_client.bank_transactions.list_all.assert_called_once_with(
        params={"account_id": "acct_1", "filter_by": "Status.Uncategorized"}
    )


def test_books_ledger_debits_are_deposits_and_credits_are_withdrawals():
    assert is_deposit_books_bank_transaction({"debit_or_credit": "debit"}) is True
    assert is_deposit_books_bank_transaction({"debit_or_credit": "credit"}) is False


def test_fetch_bank_statement_lines_keeps_books_debits_for_customer_receipts():
    books_client = MagicMock()
    books_client.bank_transactions.list_all.return_value = [
        {
            "transaction_id": "deposit_1",
            "date": "2026-07-10",
            "amount": 15000,
            "debit_or_credit": "debit",
        },
        {
            "transaction_id": "withdrawal_1",
            "date": "2026-07-10",
            "amount": 15000,
            "debit_or_credit": "credit",
        },
    ]
    config = PaymentReconciliationConfig(
        bank_account_ids=("acct_1",),
        bank_account_names={"acct_1": "HDFC"},
    )

    rows = fetch_bank_statement_lines(books_client, config)

    assert [row.id for row in rows] == ["deposit_1"]


def test_analytics_search_matches_bank_description_identifier():
    bank_line = BankStatementLine(
        id="bank_1",
        date=date(2026, 6, 20),
        amount=100.0,
        description="UPI/rjshgomathi-1@o/payment",
    )
    analytics_rows = [
        AnalyticsCustomer(customer_id="cust_1", customer_name="Rajesh Gomathi", search_key="rjshgomathi-1@okhdfcbank"),
        AnalyticsCustomer(customer_id="cust_2", customer_name="Other", search_key="someoneelse@okhdfcbank"),
    ]

    matches = analytics_search_matches_for_bank_line(bank_line, analytics_rows)

    assert [row.customer_id for row in matches] == ["cust_1"]


def test_write_separate_payment_source_csvs(tmp_path):
    bank_line = BankStatementLine(
        id="bank_1",
        date=date(2026, 6, 20),
        amount=100.0,
        description="UPI/rjshgomathi-1@o/payment",
        bank_account_id="acct_1",
        bank_name="IDFC",
        raw={"status": "uncategorized"},
    )
    creator_payment = CreatorPayment(
        id="pay_1",
        date=date(2026, 6, 20),
        amount=100.0,
        customer_id="cust_1",
        customer_name="Rajesh Gomathi",
        reference="REF1",
    )
    analytics_rows = [
        AnalyticsCustomer(customer_id="cust_1", customer_name="Rajesh Gomathi", search_key="rjshgomathi-1@okhdfcbank")
    ]

    books_path = write_unmatched_bank_statement_csv(
        [bank_line],
        analytics_rows,
        str(tmp_path / "books.csv"),
    )
    creator_path = write_creator_payments_csv(
        [creator_payment],
        str(tmp_path / "creator.csv"),
    )

    with open(books_path, newline="", encoding="utf-8") as handle:
        books_rows = list(csv.DictReader(handle))
    with open(creator_path, newline="", encoding="utf-8") as handle:
        creator_rows = list(csv.DictReader(handle))

    assert books_rows[0]["bank_name"] == "IDFC"
    assert books_rows[0]["analytics_customer_names"] == "Rajesh Gomathi"
    assert creator_rows[0]["creator_payment_id"] == "pay_1"


def test_reference_date_amount_matches_require_all_three_fields(tmp_path):
    creator_payments = [
        CreatorPayment(
            id="pay_1",
            date=date(2026, 6, 20),
            amount=305.0,
            customer_id="cust_1",
            customer_name="Customer One",
            reference="308922063469",
        ),
        CreatorPayment(
            id="pay_2",
            date=date(2026, 6, 21),
            amount=305.0,
            customer_id="cust_2",
            reference="308922063469",
        ),
    ]
    bank_lines = [
        BankStatementLine(
            id="bank_1",
            date=date(2026, 6, 20),
            amount=305.0,
            description="UPI/DR/308922063469/IDFC Fir/KKBK/idfcfir/Pay",
            bank_name="IDFC",
        )
    ]

    rows = reference_date_amount_match_rows(creator_payments, bank_lines, [])

    assert len(rows) == 1
    assert rows[0]["creator_payment_id"] == "pay_1"
    assert rows[0]["bank_transaction_id"] == "bank_1"
    assert rows[0]["matched_reference_source"] == "bank_description"

    output_path = write_reference_date_amount_matches_csv(
        creator_payments,
        bank_lines,
        [],
        str(tmp_path / "matches.csv"),
    )
    with open(output_path, newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert csv_rows[0]["match_status"] == "reference_date_amount_match"


def test_reference_date_amount_matches_accept_masked_reference_suffix():
    creator_payments = [
        CreatorPayment(
            id="pay_1",
            date=date(2026, 7, 10),
            amount=15000.0,
            customer_id="cust_1",
            reference="1965",
        ),
    ]
    bank_lines = [
        BankStatementLine(
            id="bank_1",
            date=date(2026, 7, 10),
            amount=15000.0,
            reference="xxxxxxxxxxxx1965",
            description="UPI payment",
        ),
    ]

    rows = reference_date_amount_match_rows(creator_payments, bank_lines, [])

    assert len(rows) == 1
    assert rows[0]["matched_reference"] == "1965"
    assert rows[0]["matched_reference_source"] == "bank_reference"
