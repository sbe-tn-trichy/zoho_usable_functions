import argparse
import logging
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.reconciliation.matcher import match_bank_with_vendor_ledger

logger = logging.getLogger("reconcile_bank")

def reconcile_account(client, account_id, account_name, ledger_path, date_tolerance, amount_tolerance):
    logger.info(f"================================================================================")
    logger.info(f"RECONCILING BANK ACCOUNT: {account_name} (ID: {account_id})")
    logger.info(f"================================================================================")
    
    results = match_bank_with_vendor_ledger(
        books_client=client,
        bank_account_id=account_id,
        vendor_ledger_path=ledger_path,
        date_tolerance_days=date_tolerance,
        amount_tolerance=amount_tolerance
    )
    
    logger.info(f"Reconciliation Summary:")
    logger.info(f"  - Exact Matches:  {len(results['exact_matches'])}")
    logger.info(f"  - Strong Matches: {len(results['strong_matches'])}")
    logger.info(f"  - Weak Matches:   {len(results['weak_matches'])}")
    logger.info(f"  - Unmatched Bank Transactions: {len(results['unmatched_bank_transactions'])}")
    logger.info(f"  - Unmatched Polycab Receipts:  {len(results['unmatched_ledger_receipts'])}")
    
    if results["strong_matches"]:
        print(f"\nMatches Found (Strong Matches):")
        print(f"{'Bank Tx Date':<15} {'Bank Tx Ref':<25} {'Amount':<15} | {'Ledger Date':<15} {'Ledger Ref':<18}")
        print(f"------------------------------------------------------------------------------------------------")
        for bank_tx, led_rec in results["strong_matches"]:
            bank_ref = bank_tx.get('reference_number') or bank_tx.get('cheque_number') or ""
            print(f"{bank_tx.get('date'):<15} {bank_ref:<25} {float(led_rec.get('credit_amount')):<15,} | {led_rec.get('date'):<15} {led_rec.get('transaction_no'):<18}")

def main():
    parser = argparse.ArgumentParser(description="Reconcile bank accounts against Polycab vendor ledger.")
    parser.add_argument("--ledger-path", default=Config.POLYCAB_LEDGER_PATH, help="Path to the vendor ledger Excel file")
    parser.add_argument("--date-tolerance", type=int, default=10, help="Allowed date difference in days")
    parser.add_argument("--amount-tolerance", type=float, default=0.0, help="Allowed amount difference")
    args = parser.parse_args()

    setup_logging()
    
    try:
        client = get_books_client()
    except Exception as e:
        logger.error(f"Could not initialize Zoho Books client: {e}")
        return

    # Reconcile HDFC-SBE and IDFC-SBE
    reconcile_account(client, Config.BANK_ACCOUNT_IDFC, "IDFC-SBE", args.ledger_path, args.date_tolerance, args.amount_tolerance)
    reconcile_account(client, Config.BANK_ACCOUNT_HDFC, "HDFC-SBE", args.ledger_path, args.date_tolerance, args.amount_tolerance)

if __name__ == "__main__":
    main()
