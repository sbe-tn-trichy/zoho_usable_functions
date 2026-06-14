import xlrd
import os
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from ..core.config import Config

logger = logging.getLogger(__name__)

def get_ledger_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extracts metadata (Start Date, End Date, Party Name, etc.) from the Excel ledger file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    workbook = xlrd.open_workbook(file_path)
    sheet = workbook.sheet_by_index(0)
    metadata = {
        "start_date": None,
        "end_date": None,
        "party_name": None,
        "opening_balance": 0.0
    }
    
    for r in range(min(15, sheet.nrows)):
        row = [str(sheet.cell_value(r, c)).strip() for c in range(min(sheet.ncols, 5))]
        if not row:
            continue
        first_val = row[0].lower()
        if "start date" in first_val:
            metadata["start_date"] = row[2] if len(row) > 2 else None
        elif "end date" in first_val:
            metadata["end_date"] = row[2] if len(row) > 2 else None
        elif "party name" in first_val:
            metadata["party_name"] = row[2] if len(row) > 2 else None
        elif "opening balance" in first_val:
            try:
                metadata["opening_balance"] = float(sheet.cell_value(r, 2))
            except Exception:
                pass
    return metadata

def clean_polycab_ledger(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses and cleans Polycab's reconciliation ledger Excel file (.xls).
    """
    workbook = xlrd.open_workbook(file_path)
    sheet = workbook.sheet_by_index(0)
    
    header_row_index = -1
    for r in range(sheet.nrows):
        val = sheet.cell_value(r, 0)
        if str(val).strip().lower() == "account no":
            header_row_index = r
            break
            
    if header_row_index == -1:
        raise ValueError("Could not find the Polycab header row starting with 'Account No'")
        
    headers = [str(sheet.cell_value(header_row_index, c)).strip() for c in range(sheet.ncols)]
    
    key_mapping = {
        "account no": "account_no",
        "account name": "account_name",
        "ar invoice date": "date",
        "document type": "document_type",
        "transaction no": "transaction_no",
        "transaction reference": "transaction_reference",
        "customer po no.": "customer_po_no",
        "debit amount": "debit_amount",
        "credit amount": "credit_amount",
        "closing balance": "closing_balance"
    }
    
    col_to_key = {}
    for idx, h in enumerate(headers):
        h_lower = h.lower()
        if h_lower in key_mapping:
            col_to_key[idx] = key_mapping[h_lower]
            
    transactions = []
    for r in range(header_row_index + 1, sheet.nrows):
        first_val = str(sheet.cell_value(r, 0)).strip()
        row_vals = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        
        if not any(row_vals):
            continue
            
        is_summary = False
        for val in row_vals:
            if val in ("Opening Balance", "Total Debit Amount", "Total Credit Amount", "Closing Balance"):
                is_summary = True
                break
        if is_summary:
            continue
            
        if not first_val:
            continue
            
        tx = {}
        for c, key in col_to_key.items():
            cell = sheet.cell(r, c)
            val = cell.value
            
            if key == "date":
                if cell.ctype == xlrd.XL_CELL_DATE:
                    dt = xlrd.xldate_as_datetime(val, workbook.datemode)
                    tx[key] = dt.date().isoformat()
                else:
                    tx[key] = str(val).strip()
            elif key in ("debit_amount", "credit_amount", "closing_balance"):
                try:
                    tx[key] = float(val) if val != "" else 0.0
                except (ValueError, TypeError):
                    tx[key] = 0.0
            elif key in ("account_no", "transaction_no"):
                if isinstance(val, float):
                    if val.is_integer():
                        tx[key] = str(int(val))
                    else:
                        tx[key] = str(val)
                else:
                    tx[key] = str(val).strip()
            else:
                tx[key] = str(val).strip()
                
        if tx.get("transaction_no") and tx.get("date"):
            transactions.append(tx)
            
    return transactions

def clean_ledger_file(file_path: str, vendor_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Cleans a vendor or bank ledger file using the appropriate vendor-specific cleaner.
    
    Args:
        file_path (str): Path to the ledger file.
        vendor_key (str, optional): Key identifying the vendor/bank layout (e.g. 'polycab').
                                    If not specified, determined automatically from filename.
                                    
    Returns:
        List[Dict[str, Any]]: List of cleaned transaction dictionaries.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    filename = os.path.basename(file_path)
    
    # Auto-detect vendor if not specified
    if not vendor_key:
        if filename.startswith("277498") or "polycab" in filename.lower():
            vendor_key = "polycab"
        else:
            raise ValueError(f"Could not auto-determine vendor layout for file: {filename}. Please specify vendor_key.")
            
    if vendor_key == "polycab":
        return clean_polycab_ledger(file_path)
    else:
        raise NotImplementedError(f"No cleaning implementation available for vendor key: '{vendor_key}'")
