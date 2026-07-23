import os
import sys
import argparse
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime

# Insert project src directory to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions import find_same_day_payment_anomalies

def main():
    parser = argparse.ArgumentParser(
        description="Find anomalies where a single customer has more than 1 payment entry on the same day."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date filter in YYYY-MM-DD format (defaults to beginning of current year if end-date is specified)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date filter in YYYY-MM-DD format (defaults to current date)"
    )
    parser.add_argument(
        "--customer-id",
        type=str,
        help="Filter anomalies for a specific customer ID"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/books/payment_anomalies.csv",
        help="Path to save the output CSV file"
    )

    args = parser.parse_args()

    # Ensure output directory exists
    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)

    try:
        print("Initializing Zoho Books client...")
        client = get_books_client()
        
        # Set default end date to today if start date is given and end date is not
        start = args.start_date
        end = args.end_date
        if start and not end:
            end = datetime.now().strftime("%Y-%m-%d")
        elif end and not start:
            # Default start date is beginning of current year relative to end date
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            start = f"{end_dt.year}-01-01"

        print(f"Scanning for customer payment anomalies...")
        if start or end:
            print(f"Date range: {start or 'Any'} to {end or 'Any'}")
        if args.customer_id:
            print(f"Filtering by Customer ID: {args.customer_id}")

        results = find_same_day_payment_anomalies(
            books_client=client,
            start_date=start,
            end_date=end,
            customer_id=args.customer_id
        )

        summary = results["summary"]
        anomalies = results["anomalies"]

        print("\n=== SCAN SUMMARY ===")
        print(f"Total Customer Payments Scanned: {summary['total_payments_checked']}")
        print(f"Same-Day Anomalies Detected   : {summary['total_anomalies_found']}")
        print("====================\n")

        if not anomalies:
            print("🎉 No same-day payment anomalies found for the specified criteria.")
            return

        # Print detailed report to console
        print("Detected Anomalies:")
        print("-" * 100)
        print(f"{'Customer Name':<30} | {'Customer ID':<20} | {'Date':<12} | {'Payments':<8}")
        print("-" * 100)
        
        flat_records = []
        for anomaly in anomalies:
            print(
                f"{anomaly['customer_name'][:30]:<30} | "
                f"{anomaly['customer_id']:<20} | "
                f"{anomaly['date']:<12} | "
                f"{anomaly['payment_count']:<8}"
            )
            for p in anomaly["payments"]:
                print(
                    f"  -> Payment No: {p['payment_number']:<15} | "
                    f"Amount: {p['amount']:<12.2f} | "
                    f"Mode: {p['payment_mode']:<10} | "
                    f"Ref No: {p['reference_number']}"
                )
                
                # Append for CSV export
                flat_records.append({
                    "customer_name": anomaly["customer_name"],
                    "customer_id": anomaly["customer_id"],
                    "date": anomaly["date"],
                    "payment_count": anomaly["payment_count"],
                    "payment_id": p["payment_id"],
                    "payment_number": p["payment_number"],
                    "amount": p["amount"],
                    "payment_mode": p["payment_mode"],
                    "reference_number": p["reference_number"]
                })
            print("-" * 100)

        # Export to CSV if requested
        if args.output and flat_records:
            df = pd.DataFrame(flat_records)
            df.to_csv(args.output, index=False)
            print(f"\n💾 Saved detailed anomaly report to: {args.output}")

    except Exception as e:
        print(f"❌ Error during anomaly scan: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
