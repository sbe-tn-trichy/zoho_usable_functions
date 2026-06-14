import argparse
import logging
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.reconciliation.matcher import match_bank_with_vendor_ledger

logger = logging.getLogger("run_reconciliation")

def main():
    parser = argparse.ArgumentParser(description="Scan all bank accounts for matches against external vendor ledger.")
    parser.add_argument("--ledger-path", default=Config.POLYCAB_LEDGER_PATH, help="Path to external vendor ledger file")
    parser.add_argument("--date-tolerance", type=int, default=7, help="Allowed date difference in days")
    parser.add_argument("--amount-tolerance", type=float, default=0.0, help="Allowed amount difference")
    args = parser.parse_args()

    setup_logging()
    
    try:
        client = get_books_client()
    except Exception as e:
        logger.error(f"Could not initialize Zoho Books client: {e}")
        return

    logger.info("Listing all bank accounts in Zoho Books...")
    try:
        accounts_res = client.bank_accounts.list()
        accounts = accounts_res.get("bankaccounts", [])
    except Exception as e:
        logger.error(f"Failed to fetch bank accounts: {e}")
        return
    
    bank_accounts = [acc for acc in accounts if acc.get('account_type') in ('bank', 'payment_clearing')]
    
    logger.info(f"Scanning {len(bank_accounts)} bank accounts for matches...")
    for acc in bank_accounts:
        acc_id = acc.get('account_id')
        acc_name = acc.get('account_name')
        
        try:
            results = match_bank_with_vendor_ledger(
                books_client=client,
                bank_account_id=acc_id,
                vendor_ledger_path=args.ledger_path,
                date_tolerance_days=args.date_tolerance,
                amount_tolerance=args.amount_tolerance
            )
            
            exact_count = len(results["exact_matches"])
            strong_count = len(results["strong_matches"])
            weak_count = len(results["weak_matches"])
            total_matches = exact_count + strong_count + weak_count
            
            if total_matches > 0:
                print(f"\n==================================================")
                print(f"BANK ACCOUNT MATCH FOUND!")
                print(f"Account: {acc_name} (ID: {acc_id})")
                print(f"Matches:")
                print(f"  - Exact Matches: {exact_count}")
                print(f"  - Strong Matches: {strong_count}")
                print(f"  - Weak Matches: {weak_count}")
                print(f"  - Unmatched Bank Transactions: {len(results['unmatched_bank_transactions'])}")
                print(f"  - Unmatched Ledger Receipts: {len(results['unmatched_ledger_receipts'])}")
                
                if results["exact_matches"]:
                    print("\nFirst 3 Exact Matches:")
                    for idx, (bank_tx, led_rec) in enumerate(results["exact_matches"][:3]):
                        ref_num = bank_tx.get('reference_number') or bank_tx.get('cheque_number') or ""
                        print(f"  Match {idx+1}: Date={bank_tx.get('date')} | Amount={bank_tx.get('amount')} | Ref={ref_num}")
                if results["strong_matches"]:
                    print("\nFirst 3 Strong Matches:")
                    for idx, (bank_tx, led_rec) in enumerate(results["strong_matches"][:3]):
                        print(f"  Match {idx+1}: Date={bank_tx.get('date')} | Bank Amount={bank_tx.get('amount')} | Led Amount={led_rec.get('credit_amount')}")
                
        except Exception as e:
            logger.debug(f"Error checking account {acc_name}: {e}")

if __name__ == "__main__":
    main()
