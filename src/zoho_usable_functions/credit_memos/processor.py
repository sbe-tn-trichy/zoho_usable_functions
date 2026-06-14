import os
import re
import pdfplumber
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List
from ..core.config import Config

logger = logging.getLogger(__name__)

def parse_polycab_credit_memo(pdf_path: str) -> Dict[str, Any]:
    """
    Parses a Polycab credit memo PDF using pdfplumber and extracts Credit Note details:
      - Credit Note Number (AR Invoice Number)
      - Date (Invoice Date) formatted as YYYY-MM-DD
      - Total Amount (reconciled correctly for single and multi-page layouts)
      - Description (extracted from line items)
      - Raw text (to check for GST lines)
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")
        
    logger.info(f"Parsing credit memo PDF: {pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        all_text = "\n".join([page.extract_text() for page in pdf.pages])
        
    # 1. Credit Note Number (AR Invoice Number)
    cn_match = re.search(r"AR Invoice Number[ \t]*:[ \t]*(\d+)", all_text)
    cn_num = cn_match.group(1) if cn_match else None
    if not cn_num:
        basename = os.path.basename(pdf_path)
        name_match = re.search(r"CM-(\d+)", basename)
        if name_match:
            cn_num = name_match.group(1)
            
    # 2. Date
    date_match = re.search(r"(?<!Customer\s)(?<!Customer)Invoice Date[ \t]*:[ \t]*([\w\-]+)", all_text)
    raw_date = date_match.group(1) if date_match else None
    
    formatted_date = None
    if raw_date:
        parts = raw_date.split("-")
        if len(parts) == 3:
            day, month_str, year = parts
            months = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06", 
                      "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
            month = months.get(month_str.upper(), "01")
            formatted_date = f"{year}-{month}-{day.zfill(2)}"
            
    # 3. Amount
    amount = 0.0
    total_match = re.search(r"\bTOTAL\s+([\d\.,]+)", all_text)
    if total_match:
        try:
            amount = float(total_match.group(1).replace(",", ""))
        except ValueError:
            pass
    else:
        # Scan backward from Rupees line
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]
        rupees_idx = -1
        for idx, l in enumerate(lines):
            if "rupees" in l.lower():
                rupees_idx = idx
                break
                
        if rupees_idx != -1:
            for offset in range(1, 6):
                idx = rupees_idx - offset
                if idx < 0:
                    break
                line = lines[idx]
                num_pattern = r"([\d\.,]+)\s+(\d+)\s+0\s+([\d\.,]+)\s+([\d\.,]+)"
                match = re.search(num_pattern, line)
                if match:
                    try:
                        amount = float(match.group(4).replace(",", ""))
                    except ValueError:
                        pass
                    break
                    
    # 4. Description
    description = ""
    lines = [l.strip() for l in all_text.split("\n") if l.strip()]
    rupees_idx = -1
    for idx, l in enumerate(lines):
        if "rupees" in l.lower():
            rupees_idx = idx
            break
            
    if rupees_idx != -1:
        desc_lines = []
        start_idx = 0
        for idx in range(rupees_idx - 1, -1, -1):
            if "hsn/sac" in lines[idx].lower() or "total value" in lines[idx].lower():
                start_idx = idx + 1
                break
        
        for idx in range(start_idx, rupees_idx):
            line = lines[idx]
            if line.strip().lower() in ["no", "no."]:
                continue
            num_pattern = r"([\d\.,]+)\s+(\d+)\s+0\s+([\d\.,]+)\s+([\d\.,]+)"
            match = re.search(num_pattern, line)
            if match:
                line = line[:match.start()].strip()
                if not line:
                    continue
            if line.startswith("1 ") or line == "1":
                line = line[2:].strip()
            desc_lines.append(line)
            
        description = " ".join(desc_lines).strip()
        description = re.sub(r"\s+", " ", description)
        
    if not description:
        description = f"Polycab Credit Note {cn_num or ''}"
        
    return {
        "vendor_name": "Polycab India Limited",
        "vendor_credit_number": cn_num,
        "date": formatted_date,
        "amount": amount,
        "description": description,
        "raw_text": all_text
    }

def resolve_vendor_id(books_client: Any, name: str) -> Optional[str]:
    """Finds contact ID for a vendor by name in Zoho Books."""
    res = books_client.contacts.list(params={"contact_name": name})
    contacts = res.get("contacts", [])
    if contacts:
        return contacts[0].get("contact_id")
    if "polycab" in name.lower():
        return Config.POLYCAB_VENDOR_ID
    return None

def resolve_account_id(books_client: Any, name: str) -> Optional[str]:
    """Finds account ID by name query in Zoho Books chart of accounts."""
    res = books_client.chart_of_accounts.list()
    accounts = res.get("chartofaccounts", [])
    for a in accounts:
        if name.lower() in a.get("account_name", "").lower():
            return a.get("account_id")
    for a in accounts:
        if "purchase discounts" in a.get("account_name", "").lower():
            return a.get("account_id")
    return None

def resolve_associated_bill_id(books_client: Any, vendor_id: str, credit_note_date_str: str) -> Optional[str]:
    """
    Finds an existing bill for this vendor that has a date on or before the credit note date.
    This is required in Zoho Books India to associate debit notes/credit notes for GST compliance.
    """
    bills = books_client.bills.list_all(params={"vendor_id": vendor_id})
    valid_bills = []
    
    cn_date = datetime.strptime(credit_note_date_str, "%Y-%m-%d").date()
    for b in bills:
        b_date_str = b.get("date")
        if b_date_str:
            try:
                b_date = datetime.strptime(b_date_str, "%Y-%m-%d").date()
                if b_date <= cn_date:
                    valid_bills.append((b_date, b.get("bill_id")))
            except ValueError:
                pass
                
    if valid_bills:
        valid_bills.sort(key=lambda x: x[0], reverse=True)
        return valid_bills[0][1]
    return None

def resolve_item_id(pdf_text: str) -> str:
    """
    Classifies a credit memo as a Scheme CN or RSO CN based on raw PDF text.
    Returns the corresponding Zoho Books Item ID.
    """
    text_lower = pdf_text.lower()
    
    # Check if RSO Number field is present and not empty
    rso_match = re.search(r"RSO\s+(?:Number|No\.?)\s*:\s*(\S+)", pdf_text, re.IGNORECASE)
    if rso_match and rso_match.group(1).strip():
        logger.info(f"Classified CN as RSO CN based on RSO Number: '{rso_match.group(1)}'")
        return Config.ZOHO_RSO_CN_ITEM_ID
        
    if "return type without reference" in text_lower or "ldo01" in text_lower or "llp01" in text_lower:
        return Config.ZOHO_RSO_CN_ITEM_ID
    return Config.ZOHO_SCHEME_CN_ITEM_ID

def resolve_bill_id_by_number(books_client: Any, vendor_id: str, bill_number: str) -> Optional[str]:
    """Finds the bill ID for a specific bill number under this vendor in Zoho Books."""
    res = books_client.bills.list(params={"vendor_id": vendor_id, "bill_number": bill_number})
    bills = res.get("bills", [])
    if bills:
        return bills[0].get("bill_id")
    return None

def resolve_tax_id(books_client: Any, pdf_text: str) -> str:
    """
    Determines the correct GST tax group ID in Zoho Books based on PDF text.
    Almost all credit notes are commercial/accounting CN, so we always return GST0 (no tax).
    """
    return Config.ZOHO_GST0_TAX_ID

def create_vendor_credit_from_pdf(
    books_client: Any, 
    pdf_path: str, 
    vendor_name: str = "Polycab",
    account_name: str = "Polycab Scheme - Expense"
) -> Dict[str, Any]:
    """
    Parses PDF and posts a new Vendor Credit transaction to Zoho Books.
    Omit bill_id and uses registered invoice type unless explicitly given. Sets GST Out of Scope.
    """
    details = parse_polycab_credit_memo(pdf_path)
    
    vendor_id = resolve_vendor_id(books_client, vendor_name)
    if not vendor_id:
        raise ValueError(f"Could not resolve vendor ID for name: '{vendor_name}'")
        
    bill_number_match = re.search(r'Original Tax Inv\.\s*No\.[ \t]*:[ \t]*([^\s\r\n]+)', details["raw_text"])
    bill_number = bill_number_match.group(1) if bill_number_match else None
    
    bill_id = None
    if bill_number:
        bill_id = resolve_bill_id_by_number(books_client, vendor_id, bill_number)
        
    item_id = resolve_item_id(details["raw_text"])
    
    payload = {
        "vendor_id": vendor_id,
        "vendor_credit_number": details["vendor_credit_number"],
        "date": details["date"],
        "line_items": [
            {
                "item_id": item_id,
                "rate": details["amount"],
                "quantity": 1,
                "description": details["description"],
                "gst_treatment_code": "out_of_scope"
            }
        ]
    }
    
    if bill_id:
        payload["bill_id"] = bill_id
    else:
        payload["reference_invoice_type"] = "registered"
    
    res = books_client.request('POST', 'vendorcredits', json=payload)
    return res.get("vendor_credit", res.get("vendorcredit", res))

def upload_vendor_credit_attachment(books_client: Any, vendor_credit_id: str, pdf_path: str) -> Dict[str, Any]:
    """Attaches PDF file to a Vendor Credit in Zoho Books."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")
    filename = os.path.basename(pdf_path)
    with open(pdf_path, 'rb') as f:
        files = {
            'attachment': (filename, f, 'application/pdf')
        }
        return books_client.request('POST', f"vendorcredits/{vendor_credit_id}/attachment", files=files)

def upload_to_workdrive(wd_client: Any, folder_id: str, pdf_path: str) -> Dict[str, Any]:
    """Uploads PDF file to Zoho WorkDrive folder."""
    return wd_client.files.upload(folder_id, pdf_path)
