import os
import argparse
import logging
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client, get_workdrive_client, fetch_access_tokens
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.credit_memos.processor import (
    parse_polycab_credit_memo,
    create_vendor_credit_from_pdf,
    upload_vendor_credit_attachment,
    upload_to_workdrive
)
from zoho_usable_functions.reconciliation.matcher import fetch_vendor_credits

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
        return

    # 1. Fetch existing vendor credits in Zoho Books to prevent duplicates
    logger.info("Fetching existing vendor credits in Zoho Books...")
    existing_credits = fetch_vendor_credits(books_client, {"vendor_id": args.vendor_id})
    existing_credit_numbers = {c.get("vendor_credit_number") for c in existing_credits if c.get("vendor_credit_number")}
    logger.info(f"Found {len(existing_credit_numbers)} existing vendor credits in Books.")
    
    # 2. Fetch existing files in WorkDrive target folder to prevent duplicate uploads
    logger.info("Fetching existing files in Zoho WorkDrive folder...")
    try:
        wd_files = wd_client.files.list_all_files(args.folder_id)
        existing_wd_filenames = {f.get("attributes", {}).get("name") for f in wd_files}
    except Exception as e:
        logger.warning(f"Could not list WorkDrive folder contents: {e}")
        existing_wd_filenames = set()
    logger.info(f"Found {len(existing_wd_filenames)} files in target WorkDrive folder.")

    # Get all PDF files to process
    if not os.path.exists(args.files_dir):
        logger.error(f"Files directory not found: {args.files_dir}")
        return
        
    pdf_files = sorted([f for f in os.listdir(args.files_dir) if f.endswith(".pdf") and (f.startswith("CM-") or f.startswith("CN-"))])
    if not pdf_files:
        logger.info(f"No CM- or CN- PDF files found in {args.files_dir} folder.")
        return
        
    logger.info(f"Processing {len(pdf_files)} PDF credit memos...")
    
    summary = {
        "processed": 0,
        "books_created": 0,
        "books_skipped": 0,
        "wd_uploaded": 0,
        "wd_skipped": 0,
        "errors": 0
    }
    
    for f in pdf_files:
        file_path = os.path.join(args.files_dir, f)
        logger.info(f"--------------------------------------------------")
        logger.info(f"File: {f}")
        
        try:
            # Step 1: Parse PDF
            details = parse_polycab_credit_memo(file_path)
            cn_num = details["vendor_credit_number"]
            amount = details["amount"]
            date_str = details["date"]
            
            logger.info(f"Parsed details: CN={cn_num} | Date={date_str} | Amount={amount}")
            summary["processed"] += 1
            
            if not cn_num or amount <= 0:
                logger.error("Invalid details parsed. Skipping.")
                summary["errors"] += 1
                continue
                
            # Step 2: Create Vendor Credit in Zoho Books
            vc_id = None
            if cn_num in existing_credit_numbers:
                logger.info(f"Vendor credit {cn_num} already exists in Zoho Books. Skipping creation.")
                summary["books_skipped"] += 1
                for c in existing_credits:
                    if c.get("vendor_credit_number") == cn_num:
                        vc_id = c.get("vendor_credit_id")
                        break
            else:
                logger.info("Creating vendor credit in Zoho Books...")
                vc = create_vendor_credit_from_pdf(books_client, file_path)
                vc_id = vc.get("vendor_credit_id")
                logger.info(f"Vendor credit successfully created in Books (ID: {vc_id}).")
                summary["books_created"] += 1
                existing_credit_numbers.add(cn_num)
                
            # Step 3: Attach PDF in Zoho Books
            if vc_id:
                try:
                    logger.info("Attaching PDF to vendor credit in Books...")
                    upload_vendor_credit_attachment(books_client, vc_id, file_path)
                    logger.info("PDF attached to vendor credit successfully.")
                except Exception as e:
                    logger.warning(f"Could not attach PDF to Zoho Books: {e}")
            
            # Step 4: Upload to WorkDrive
            if f in existing_wd_filenames:
                logger.info("File already exists in Zoho WorkDrive folder. Skipping upload.")
                summary["wd_skipped"] += 1
            else:
                logger.info("Uploading file to Zoho WorkDrive...")
                upload_to_workdrive(wd_client, args.folder_id, file_path)
                logger.info("File successfully uploaded to WorkDrive.")
                summary["wd_uploaded"] += 1
                existing_wd_filenames.add(f)
                
        except Exception as e:
            logger.error(f"Error processing file {f}: {e}")
            summary["errors"] += 1

    logger.info(f"==================================================")
    logger.info(f"PROCESSING SUMMARY")
    logger.info(f"==================================================")
    logger.info(f"Total files:                  {len(pdf_files)}")
    logger.info(f"Successfully processed:       {summary['processed']}")
    logger.info(f"Zoho Books Credits Created:   {summary['books_created']}")
    logger.info(f"Zoho Books Credits Skipped:   {summary['books_skipped']}")
    logger.info(f"Zoho WorkDrive Uploads:       {summary['wd_uploaded']}")
    logger.info(f"Zoho WorkDrive Skipped:       {summary['wd_skipped']}")
    logger.info(f"Errors encountered:           {summary['errors']}")
    logger.info(f"==================================================")

if __name__ == "__main__":
    main()
