import argparse
import os
import sys

import pandas as pd

# Insert project src directory to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions import find_customers_with_unused_credits


def main():
    parser = argparse.ArgumentParser(description="Find active customers with unused credits in Zoho Books.")
    parser.add_argument(
        "--output",
        type=str,
        default="output/books/customers_with_unused_credits.csv",
        help="Path to save the output CSV file",
    )
    parser.add_argument(
        "--min-unused-credit-amount",
        type=float,
        default=0.0,
        help="Minimum unused credit amount to include in the report",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize phone numbers in the exported customer records",
    )
    args = parser.parse_args()

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)

    try:
        print("Initializing Zoho Books client...")
        client = get_books_client()
        results = find_customers_with_unused_credits(
            books_client=client,
            normalize=args.normalize,
            min_unused_credit_amount=args.min_unused_credit_amount,
        )

        summary = results["summary"]
        customers = results["customers"]

        print("\n=== UNUSED CREDITS SUMMARY ===")
        print(f"Total Customers Checked      : {summary['total_customers_checked']}")
        print(f"Customers With Unused Credits: {summary['customers_with_unused_credits']}")
        print(f"Total Unused Credit Amount   : {summary['total_unused_credit_amount']:.2f}")
        print("==============================\n")

        if not customers:
            print("No active customers with unused credits were found for the selected threshold.")
            return

        print("Customers with unused credits:")
        print("-" * 110)
        print(f"{'Customer Name':<35} | {'Customer ID':<20} | {'Unused Credit':<15} | {'Company':<30}")
        print("-" * 110)

        for customer in customers:
            print(
                f"{(customer['contact_name'] or '')[:35]:<35} | "
                f"{(customer['contact_id'] or ''):<20} | "
                f"{customer['unused_credits_receivable_amount']:<15.2f} | "
                f"{(customer['company_name'] or '')[:30]:<30}"
            )

        if args.output:
            df = pd.DataFrame(customers)
            df.to_csv(args.output, index=False)
            print(f"\n💾 Saved unused credit report to: {args.output}")

    except Exception as exc:
        print(f"❌ Error finding customers with unused credits: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
