import argparse
import logging
from datetime import datetime

from zoho_usable_functions.core.auth import get_analytics_token, get_books_client, get_creator_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.payment_reconciliation import (
    PaymentReconciliationConfig,
    fetch_analytics_customer_table,
    fetch_creator_payments,
    fetch_unmatched_bank_statement_lines,
    write_creator_payments_csv,
    write_reference_date_amount_matches_csv,
    write_unmatched_bank_statement_csv,
)

logger = logging.getLogger("payment_reconciliation")


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Export payment reconciliation source CSV files.")
    parser.add_argument("--creator-app", help="Zoho Creator app link name")
    parser.add_argument("--creator-report", help="Zoho Creator report link name")
    parser.add_argument("--analytics-workspace-id", help="Zoho Analytics workspace ID")
    parser.add_argument("--analytics-view-id", help="Zoho Analytics customer finder query table/view ID")
    parser.add_argument("--bank-account-id", action="append", dest="bank_account_ids", help="Books bank account ID; repeat for multiple")
    parser.add_argument("--from-date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to-date", help="End date YYYY-MM-DD")
    parser.add_argument("--creator-criteria", help="Optional Creator report criteria")
    parser.add_argument(
        "--books-output-csv",
        default="output/payment_reconciliation/books_uncategorized_bank_transactions.csv",
        help="CSV path for Books bank transactions fetched with filter_by=Status.Uncategorized",
    )
    parser.add_argument(
        "--creator-output-csv",
        default="output/payment_reconciliation/creator_payments.csv",
        help="CSV path for Creator payments",
    )
    parser.add_argument(
        "--matches-output-csv",
        default="output/payment_reconciliation/reference_date_amount_matches.csv",
        help="CSV path for matches found by reference number, date, and amount",
    )
    args = parser.parse_args()

    setup_logging()

    default_config = PaymentReconciliationConfig()
    config = PaymentReconciliationConfig(
        creator_app_link_name=args.creator_app or default_config.creator_app_link_name,
        creator_report_link_name=args.creator_report or default_config.creator_report_link_name,
        analytics_workspace_id=args.analytics_workspace_id or default_config.analytics_workspace_id,
        analytics_view_id=args.analytics_view_id or default_config.analytics_view_id,
        bank_account_ids=tuple(args.bank_account_ids) if args.bank_account_ids else default_config.bank_account_ids,
        start_date=_parse_date(args.from_date),
        end_date=_parse_date(args.to_date),
        creator_criteria=args.creator_criteria,
    )

    books_client = get_books_client()
    creator_client = get_creator_client()
    analytics_token = get_analytics_token()

    creator_payments = fetch_creator_payments(creator_client, config)
    bank_lines = fetch_unmatched_bank_statement_lines(books_client, config)
    analytics_rows = fetch_analytics_customer_table(analytics_token, config)

    books_csv = write_unmatched_bank_statement_csv(bank_lines, analytics_rows, args.books_output_csv)
    creator_csv = write_creator_payments_csv(creator_payments, args.creator_output_csv)
    matches_csv = write_reference_date_amount_matches_csv(
        creator_payments,
        bank_lines,
        analytics_rows,
        args.matches_output_csv,
    )

    print("Payment reconciliation exports")
    print("  Books filter: filter_by=Status.Uncategorized")
    print(f"  Books uncategorized bank transactions: {len(bank_lines)}")
    print(f"  Creator payments: {len(creator_payments)}")
    print(f"  Analytics search rows loaded: {len(analytics_rows)}")
    print(f"  Books CSV: {books_csv}")
    print(f"  Creator CSV: {creator_csv}")
    print(f"  Matches CSV: {matches_csv}")


if __name__ == "__main__":
    main()
