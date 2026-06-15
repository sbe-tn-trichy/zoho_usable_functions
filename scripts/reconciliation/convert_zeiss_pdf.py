#!/usr/bin/env python3
"""
Parse Carl Zeiss ledger PDFs in files/zeiss/ledgers/ and consolidate them into a CSV file.

Usage:
    uv run python scripts/reconciliation/convert_zeiss_pdf.py
"""
import os
import re
import csv
import logging
from datetime import datetime
import pdfplumber

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("convert_zeiss_pdf")

# Map of month abbreviations to full month names
MONTH_MAP = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December"
}

def parse_month_from_filename(filename: str) -> str:
    """Extract Statement Month (e.g., 'December 2024') from the filename."""
    # Pattern to match: e.g. "Dec 2024" or "Dec 2024_1"
    match = re.search(r'([A-Za-z]{3})\s+(\d{4})', filename)
    if not match:
        raise ValueError(f"Could not parse month/year from filename: {filename}")
    
    month_abbr = match.group(1).lower()
    year = match.group(2)
    
    full_month = MONTH_MAP.get(month_abbr)
    if not full_month:
        raise ValueError(f"Unknown month abbreviation: {month_abbr} in filename: {filename}")
        
    return f"{full_month} {year}"

def format_amount(val_str: str) -> str:
    """Format numeric string to match existing CSV conventions (no decimals for integer amounts)."""
    try:
        val = float(val_str)
        if val == 0.0:
            return "0"
        if val.is_integer():
            return str(int(val))
        return f"{val:.2f}"
    except ValueError:
        return val_str

def parse_pdf_statement(pdf_path: str) -> list:
    """Parse transaction lines from a Zeiss PDF statement."""
    filename = os.path.basename(pdf_path)
    try:
        statement_month = parse_month_from_filename(filename)
    except ValueError as e:
        logger.error(e)
        statement_month = "Unknown"

    rows = []
    
    with pdfplumber.open(pdf_path) as pdf:
        logger.info(f"Parsing {filename} ({len(pdf.pages)} pages)...")
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            
            for line in text.split('\n'):
                # Transaction lines start with a date of form DD.MM.YYYY
                if re.match(r'^\d{2}\.\d{2}\.\d{4}', line):
                    tokens = line.split()
                    if len(tokens) < 6:
                        logger.warning(f"Skipping line with too few tokens: {line}")
                        continue
                    
                    posting_date = tokens[0]
                    document_no = tokens[1]
                    
                    # Distinguish credit/debit note (2-word Voucher Type) from standard invoice/receipt
                    if tokens[-4] == "Note":
                        voucher_type = f"{tokens[-5]} {tokens[-4]}"
                        debit = tokens[-3]
                        credit = tokens[-2]
                        closing_balance = tokens[-1]
                        middle_tokens = tokens[2:-5]
                    else:
                        voucher_type = tokens[-4]
                        debit = tokens[-3]
                        credit = tokens[-2]
                        closing_balance = tokens[-1]
                        middle_tokens = tokens[2:-4]
                    
                    # Decode middle tokens to find invoice number and due date
                    if len(middle_tokens) == 0:
                        invoice_number = ""
                        due_date = ""
                    elif len(middle_tokens) == 1:
                        invoice_number = middle_tokens[0]
                        due_date = ""
                    else:
                        invoice_number = middle_tokens[0]
                        due_date = middle_tokens[1]
                    
                    rows.append({
                        "Statement Month": statement_month,
                        "Posting Date": posting_date,
                        "Document No": document_no,
                        "Invoice Number": invoice_number,
                        "Due Date": due_date,
                        "Voucher Type": voucher_type,
                        "Debit": format_amount(debit),
                        "Credit": format_amount(credit),
                        "Closing Balance": format_amount(closing_balance),
                        "Remarks": ""
                    })
                    
    logger.info(f"Extracted {len(rows)} entries from {filename}")
    return rows

def main():
    workspace_dir = "/Users/vak/Documents/workspace/zoho_usable_functions"
    ledgers_dir = os.path.join(workspace_dir, "files/zeiss/ledgers")
    output_path = os.path.join(workspace_dir, "files/zeiss/Consolidated_Zeiss_Statements_2024_2025.csv")
    
    if not os.path.isdir(ledgers_dir):
        logger.error(f"Ledgers directory does not exist: {ledgers_dir}")
        return
        
    pdf_files = [f for f in os.listdir(ledgers_dir) if f.endswith('.pdf')]
    if not pdf_files:
        logger.error(f"No PDF files found in {ledgers_dir}")
        return
        
    all_rows = []
    for pdf_file in sorted(pdf_files):
        pdf_path = os.path.join(ledgers_dir, pdf_file)
        all_rows.extend(parse_pdf_statement(pdf_path))
        
    # De-duplicate identical physical transactions (due to statement overlaps)
    # Key is (Document No, Posting Date, Voucher Type, Debit, Credit)
    seen = {}
    for row in all_rows:
        key = (row["Document No"], row["Posting Date"], row["Voucher Type"], row["Debit"], row["Credit"])
        if key not in seen:
            seen[key] = row
        else:
            # Resolve which one is correct by comparing actual posting date's month with Statement Month
            try:
                p_date = datetime.strptime(row["Posting Date"], "%d.%m.%Y")
                p_month_year = p_date.strftime("%B %Y")
            except ValueError:
                p_month_year = None
                
            existing = seen[key]
            if p_month_year and row["Statement Month"] == p_month_year and existing["Statement Month"] != p_month_year:
                seen[key] = row
                
    deduped_rows = list(seen.values())
    logger.info(f"De-duplicated {len(all_rows)} transactions down to {len(deduped_rows)} unique entries")
        
    # Chronologically sort rows based on posting date (DD.MM.YYYY)
    deduped_rows.sort(key=lambda r: datetime.strptime(r["Posting Date"], "%d.%m.%Y"))
    
    # Save to CSV
    headers = [
        "Statement Month",
        "Posting Date",
        "Document No",
        "Invoice Number",
        "Due Date",
        "Voucher Type",
        "Debit",
        "Credit",
        "Closing Balance",
        "Remarks"
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(deduped_rows)
        
    logger.info(f"Consolidated CSV created with {len(deduped_rows)} transactions at: {output_path}")

if __name__ == "__main__":
    main()
