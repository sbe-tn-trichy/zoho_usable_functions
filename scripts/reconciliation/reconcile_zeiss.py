"""
Reconcile Zoho Books Carl Zeiss vendor account against the Zeiss CSV statement.

Usage:
    uv run python scripts/reconciliation/reconcile_zeiss.py
    uv run python scripts/reconciliation/reconcile_zeiss.py --vendor-id 1094368000002502821 --ledger-path files/zeiss/...csv
"""
import argparse
import logging
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.reconciliation.matcher import reconcile_vendor_account

logger = logging.getLogger("reconcile_zeiss")

def main():
    parser = argparse.ArgumentParser(description="Reconcile Zoho Books Zeiss vendor account with the Zeiss CSV statement.")
    parser.add_argument("--vendor-id",    default=Config.ZEISS_VENDOR_ID,  help="Zoho Books vendor ID for Zeiss")
    parser.add_argument("--ledger-path",  default=Config.ZEISS_LEDGER_PATH, help="Path to the Zeiss CSV statement")
    parser.add_argument("--date-tolerance",   type=int,   default=7,    help="Allowed date difference in days")
    parser.add_argument("--amount-tolerance", type=float, default=0.05, help="Allowed amount difference (₹)")
    parser.add_argument("--output-diff",  help="Path to save the unmatched transaction diff (CSV)")
    args = parser.parse_args()

    setup_logging()

    try:
        client = get_books_client()
    except Exception as e:
        logger.error(f"Could not initialize Zoho Books client: {e}")
        return

    logger.info(f"Reconciling Zeiss (vendor_id={args.vendor_id}) against: {args.ledger_path}")

    results = reconcile_vendor_account(
        books_client=client,
        vendor_id=args.vendor_id,
        vendor_ledger_path=args.ledger_path,
        date_tolerance_days=args.date_tolerance,
        amount_tolerance=args.amount_tolerance,
    )

    doc_types = [
        ("sales_invoice", "Sales Invoice / Bill",  "Bill Number",      "total",  "debit_amount"),
        ("receipt",       "Receipt / Payment",      "Payment ID",       "amount", "credit_amount"),
        ("credit_memo",   "Credit Note",            "Credit Note No",   "total",  "credit_amount"),
        ("debit_memo",    "Debit Note",             "Debit Note No",    "total",  "debit_amount"),
    ]

    grand_matched = grand_unmatched_books = grand_unmatched_ledger = 0

    print(f"\n{'='*70}")
    print(f"RECONCILIATION — CARL ZEISS INDIA (BANGALORE) PVT LTD")
    print(f"Vendor ID : {args.vendor_id}")
    print(f"Ledger    : {args.ledger_path}")
    print(f"{'='*70}")

    for key, display_name, books_ref_header, books_amt_key, ledger_amt_key in doc_types:
        group            = results[key]
        matches          = group["matches"]
        unmatched_books  = group["unmatched_books"]
        unmatched_ledger = group["unmatched_ledger"]

        grand_matched          += len(matches)
        grand_unmatched_books  += len(unmatched_books)
        grand_unmatched_ledger += len(unmatched_ledger)

        print(f"\n▸ {display_name.upper()}")
        print(f"  Matched            : {len(matches)}")
        print(f"  Unmatched (Books)  : {len(unmatched_books)}")
        print(f"  Unmatched (Ledger) : {len(unmatched_ledger)}")

        if matches:
            print(f"\n  First 10 matched {display_name}s:")
            hdr = f"  {'Books Ref':<30} {'Books Date':<12} {'Amount':>12}  {'Ledger Ref':<30} {'Ledger Date':<12}"
            print(hdr)
            print(f"  {'-'*100}")
            for books_item, ledger_item in matches[:10]:
                if key == "receipt":
                    b_ref = books_item.get("payment_id") or books_item.get("id") or ""
                else:
                    b_ref = (books_item.get("bill_number")
                             or books_item.get("vendor_credit_number")
                             or books_item.get("id") or "")
                b_amt  = abs(float(books_item.get(books_amt_key) or 0.0))
                l_ref  = ledger_item.get("transaction_no") or ""
                l_date = ledger_item.get("date") or ""
                b_date = books_item.get("date") or ""
                print(f"  {b_ref:<30} {b_date:<12} {b_amt:>12,.2f}  {l_ref:<30} {l_date:<12}")

        if unmatched_books:
            print(f"\n  ⚠ In Books but NOT in Ledger ({len(unmatched_books)}):")
            print(f"  {books_ref_header:<30} {'Date':<12} {'Amount':>12}")
            print(f"  {'-'*60}")
            for item in unmatched_books:
                if key == "receipt":
                    ref = item.get("payment_id") or item.get("id") or ""
                else:
                    ref = (item.get("bill_number")
                           or item.get("vendor_credit_number")
                           or item.get("id") or "")
                amt = abs(float(item.get(books_amt_key) or 0.0))
                print(f"  {ref:<30} {item.get('date'):<12} {amt:>12,.2f}")

        if unmatched_ledger:
            print(f"\n  ⚠ In Ledger but NOT in Books ({len(unmatched_ledger)}):")
            print(f"  {'Ledger Ref':<30} {'Date':<12} {'Amount':>12}")
            print(f"  {'-'*60}")
            for item in unmatched_ledger:
                ref = item.get("transaction_no") or ""
                amt = abs(float(item.get(ledger_amt_key) or 0.0))
                print(f"  {ref:<30} {item.get('date'):<12} {amt:>12,.2f}")

    print(f"\n{'='*70}")
    print(f"GRAND SUMMARY")
    print(f"{'='*70}")
    print(f"  Total Matched            : {grand_matched}")
    print(f"  Total Unmatched (Books)  : {grand_unmatched_books}")
    print(f"  Total Unmatched (Ledger) : {grand_unmatched_ledger}")
    match_rate = (grand_matched / (grand_matched + grand_unmatched_books + grand_unmatched_ledger) * 100) \
        if (grand_matched + grand_unmatched_books + grand_unmatched_ledger) else 0
    print(f"  Overall Match Rate       : {match_rate:.1f}%")
    print(f"{'='*70}\n")

    # Construct a default output path if not specified
    if not args.output_diff:
        import os
        import re
        ledger_name = os.path.splitext(os.path.basename(args.ledger_path))[0]
        safe_ledger_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', ledger_name)
        args.output_diff = f"output/reconciliation_diff_{safe_ledger_name}.csv"

    # Write unmatched diff to CSV
    try:
        import os
        import csv
        headers = ["Source", "Document Type", "Reference", "Date", "Amount", "Books Value", "Ledger Value", "Difference"]
        diff_rows = []
        
        for key, display_name, _, books_amt_key, ledger_amt_key in doc_types:
            group = results[key]
            unmatched_books = group["unmatched_books"]
            unmatched_ledger = group["unmatched_ledger"]
            
            # Map unmatched ledger items by reference
            ledger_by_ref = {}
            for item in unmatched_ledger:
                ref = (item.get("transaction_no") or "").strip().lower()
                if ref:
                    ledger_by_ref[ref] = item
            
            matched_ledger_refs = set()
            
            # Identify paired mismatches and standalone books entries
            for item in unmatched_books:
                if key == "receipt":
                    ref = (item.get("payment_id") or item.get("id") or "").strip()
                else:
                    ref = (item.get("bill_number") or item.get("vendor_credit_number") or item.get("id") or "").strip()
                
                ref_lower = ref.lower()
                if ref_lower in ledger_by_ref:
                    ledger_item = ledger_by_ref[ref_lower]
                    matched_ledger_refs.add(ref_lower)
                    
                    b_val = abs(float(item.get(books_amt_key) or 0.0))
                    l_val = abs(float(ledger_item.get(ledger_amt_key) or 0.0))
                    diff = b_val - l_val
                    
                    diff_rows.append({
                        "Source": "Amount Mismatch",
                        "Document Type": display_name,
                        "Reference": ref,
                        "Date": item.get("date") or ledger_item.get("date") or "",
                        "Amount": "",
                        "Books Value": f"{b_val:.2f}",
                        "Ledger Value": f"{l_val:.2f}",
                        "Difference": f"{diff:.2f}"
                    })
                else:
                    amt = abs(float(item.get(books_amt_key) or 0.0))
                    diff_rows.append({
                        "Source": "Zoho Books",
                        "Document Type": display_name,
                        "Reference": ref,
                        "Date": item.get("date") or "",
                        "Amount": f"{amt:.2f}",
                        "Books Value": "",
                        "Ledger Value": "",
                        "Difference": ""
                    })
            
            # Add remaining standalone ledger entries
            for item in unmatched_ledger:
                ref = (item.get("transaction_no") or "").strip()
                if ref.lower() not in matched_ledger_refs:
                    amt = abs(float(item.get(ledger_amt_key) or 0.0))
                    diff_rows.append({
                        "Source": "Zeiss Ledger",
                        "Document Type": display_name,
                        "Reference": ref,
                        "Date": item.get("date") or "",
                        "Amount": f"{amt:.2f}",
                        "Books Value": "",
                        "Ledger Value": "",
                        "Difference": ""
                    })
        
        os.makedirs(os.path.dirname(args.output_diff), exist_ok=True)
        with open(args.output_diff, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(diff_rows)
        print(f"Reconciliation diff successfully saved to: {args.output_diff}\n")
    except Exception as e:
        logger.error(f"Failed to write reconciliation diff CSV: {e}")


if __name__ == "__main__":
    main()
