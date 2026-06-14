import argparse
import logging
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.reconciliation.matcher import reconcile_vendor_account

logger = logging.getLogger("reconcile_vendor")

def main():
    parser = argparse.ArgumentParser(description="Reconcile Zoho Books vendor account with external vendor ledger.")
    parser.add_argument("--vendor-id", default=Config.POLYCAB_VENDOR_ID, help="Zoho Books vendor ID")
    parser.add_argument("--ledger-path", default=Config.POLYCAB_LEDGER_PATH, help="Path to external vendor ledger file")
    parser.add_argument("--date-tolerance", type=int, default=20, help="Allowed date difference in days")
    parser.add_argument("--amount-tolerance", type=float, default=0.05, help="Allowed amount difference")
    args = parser.parse_args()

    setup_logging()
    
    try:
        client = get_books_client()
    except Exception as e:
        logger.error(f"Could not initialize Zoho Books client: {e}")
        return

    logger.info(f"Reconciling Zoho Books Vendor Account for ID: {args.vendor_id} with ledger: {args.ledger_path}...")
    
    results = reconcile_vendor_account(
        books_client=client,
        vendor_id=args.vendor_id,
        vendor_ledger_path=args.ledger_path,
        date_tolerance_days=args.date_tolerance,
        amount_tolerance=args.amount_tolerance
    )
    
    print(f"\n==================================================")
    print(f"RECONCILIATION SUMMARY FOR VENDOR ID: {args.vendor_id}")
    print(f"==================================================")
    
    doc_types = [
        ("sales_invoice", "Sales Invoice", "Bill No", "total", "debit_amount"),
        ("receipt", "Receipt", "Payment ID", "amount", "credit_amount"),
        ("credit_memo", "Credit Memo", "Credit Note No", "total", "credit_amount"),
        ("debit_memo", "Debit Memo", "Debit Note/Bill No", "total", "debit_amount")
    ]
    
    for key, display_name, books_ref_header, books_amt_key, ledger_amt_key in doc_types:
        group = results[key]
        matches = group["matches"]
        unmatched_books = group["unmatched_books"]
        unmatched_ledger = group["unmatched_ledger"]
        
        print(f"\nDOCUMENT TYPE: {display_name.upper()}")
        print(f"--------------------------------------------------")
        print(f"  - Matched Entries:            {len(matches)}")
        print(f"  - Unmatched Zoho Books:       {len(unmatched_books)}")
        print(f"  - Unmatched Ledger:           {len(unmatched_ledger)}")
        
        # Print first 5 matches
        if matches:
            print(f"\n    First 5 Matched {display_name}s:")
            print(f"    {'Books Ref':<25} {'Books Date':<12} {'Amount':<15} | {'Ledger Ref':<20} {'Ledger Date':<12}")
            print(f"    {'-'*95}")
            for books_item, ledger_item in matches[:5]:
                if key == "sales_invoice":
                    b_ref = books_item.get("bill_number") or ""
                elif key == "receipt":
                    b_ref = books_item.get("payment_id") or books_item.get("id") or ""
                elif key == "credit_memo":
                    b_ref = books_item.get("vendor_credit_number") or ""
                elif key == "debit_memo":
                    b_ref = books_item.get("bill_number") or ""
                else:
                    b_ref = books_item.get("id") or ""
                    
                b_amt = float(books_item.get(books_amt_key) or 0.0)
                l_ref = ledger_item.get("transaction_no") or ""
                l_date = ledger_item.get("date") or ""
                print(f"    {b_ref:<25} {books_item.get('date'):<12} {abs(b_amt):<15,} | {l_ref:<20} {l_date:<12}")
                
        # Print unmatched Zoho Books
        if unmatched_books:
            print(f"\n    Zoho Books {display_name}s Missing in Ledger ({len(unmatched_books)}):")
            print(f"    {books_ref_header:<25} {'Date':<12} {'Amount':<15}")
            print(f"    {'-'*60}")
            for item in unmatched_books:
                if key == "sales_invoice":
                    ref = item.get("bill_number") or ""
                elif key == "receipt":
                    ref = item.get("payment_id") or item.get("id") or ""
                elif key == "credit_memo":
                    ref = item.get("vendor_credit_number") or ""
                elif key == "debit_memo":
                    ref = item.get("bill_number") or ""
                else:
                    ref = item.get("id") or ""
                amt = float(item.get(books_amt_key) or 0.0)
                print(f"    {ref:<25} {item.get('date'):<12} {abs(amt):<15,}")
                
        # Print unmatched Ledger
        if unmatched_ledger:
            print(f"\n    Ledger {display_name}s Missing in Books ({len(unmatched_ledger)}):")
            print(f"    {'Ledger Tx No':<25} {'Date':<12} {'Amount':<15}")
            print(f"    {'-'*60}")
            for item in unmatched_ledger:
                ref = item.get("transaction_no") or ""
                amt = float(item.get(ledger_amt_key) or 0.0)
                print(f"    {ref:<25} {item.get('date'):<12} {abs(amt):<15,}")

if __name__ == "__main__":
    main()
