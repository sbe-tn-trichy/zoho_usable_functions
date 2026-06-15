import os
import sys
import argparse
import logging

# Inject src directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client, get_workdrive_client, fetch_access_tokens
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.credit_memos.processor import process_polycab_credit_memos

logger = logging.getLogger("process_credit_memo")

def main():
    parser = argparse.ArgumentParser(description="Process Polycab credit memo PDFs, post to Zoho Books, and upload to Zoho WorkDrive.")
    parser.add_argument("--files-dir", default=Config.FILES_DIR, help="Directory containing credit memo PDFs")
    parser.add_argument("--folder-id", default=Config.POLYCAB_FOLDER_ID, help="Zoho WorkDrive target folder ID")
    parser.add_argument("--vendor-id", default=Config.POLYCAB_VENDOR_ID, help="Zoho Books vendor ID for Polycab")
    args = parser.parse_args()

    setup_logging()
    
    logger.info("Initializing Zoho clients...")
    try:
        tokens = fetch_access_tokens()
        books_client = get_books_client(token=tokens.get("books"))
        wd_client = get_workdrive_client(token=tokens.get("workdrive"))
    except Exception as e:
        logger.error(f"Could not initialize Zoho API clients: {e}")
        sys.exit(1)

    try:
        summary = process_polycab_credit_memos(
            books_client=books_client,
            wd_client=wd_client,
            files_dir=args.files_dir,
            folder_id=args.folder_id,
            vendor_id=args.vendor_id
        )
    except Exception as e:
        logger.error(f"Processing credit memos failed with error: {e}")
        sys.exit(1)

    logger.info(f"==================================================")
    logger.info(f"PROCESSING SUMMARY")
    logger.info(f"==================================================")
    logger.info(f"Total files:                  {summary['total_files']}")
    logger.info(f"Successfully processed:       {summary['processed']}")
    logger.info(f"Zoho Books Credits Created:   {summary['books_created']}")
    logger.info(f"Zoho Books Credits Skipped:   {summary['books_skipped']}")
    logger.info(f"Zoho WorkDrive Uploads:       {summary['wd_uploaded']}")
    logger.info(f"Zoho WorkDrive Skipped:       {summary['wd_skipped']}")
    logger.info(f"Errors encountered:           {summary['errors']}")
    logger.info(f"==================================================")

if __name__ == "__main__":
    main()
