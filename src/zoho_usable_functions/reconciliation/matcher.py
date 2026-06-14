import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from .cleaner import clean_ledger_file, get_ledger_metadata

logger = logging.getLogger(__name__)

def parse_date(date_str: Any) -> Optional[date]:
    """Safely parse various date formats into a datetime.date object."""
    if not date_str:
        return None
    if isinstance(date_str, (date, datetime)):
        return date_str if isinstance(date_str, date) else date_str.date()
    try:
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(str(date_str).strip().split('T')[0]).date()
        except ValueError:
            return None

def get_abs_amount(tx: Dict[str, Any]) -> float:
    """Extract absolute amount from a bank transaction dict."""
    try:
        return abs(float(tx.get("amount", 0.0)))
    except (ValueError, TypeError):
        return 0.0

def ref_match(ref1: Any, ref2: Any) -> bool:
    """Compare two reference numbers case-insensitively and stripped of whitespace."""
    r1 = str(ref1 or "").strip().lower()
    r2 = str(ref2 or "").strip().lower()
    return bool(r1 and r2 and r1 == r2)

def match_ledger_entries(
    books_client: Any,
    bank_account_id: str,
    vendor_id: str,
    date_tolerance_days: int = 7,
    amount_tolerance: float = 0.0
) -> Dict[str, Any]:
    """
    Matches Bank Account transactions (money out/withdrawals) with Vendor Payments in Zoho Books.
    """
    logger.info(f"Fetching bank transactions for bank account ID: {bank_account_id}")
    bank_txs = books_client.bank_transactions.list_all(params={"account_id": bank_account_id})
    
    withdrawals = []
    for tx in bank_txs:
        amount_val = 0.0
        try:
            amount_val = float(tx.get("amount", 0.0))
        except (ValueError, TypeError):
            pass
            
        is_withdrawal = False
        if amount_val < 0:
            is_withdrawal = True
        elif str(tx.get("debit_or_credit")).lower() == "debit":
            is_withdrawal = True
        elif str(tx.get("transaction_type")).lower() in ("expense", "withdrawal", "payment"):
            is_withdrawal = True
        elif str(tx.get("type")).lower() in ("expense", "withdrawal", "payment"):
            is_withdrawal = True
            
        if is_withdrawal:
            withdrawals.append(tx)
            
    logger.info(f"Fetching vendor payments for vendor ID: {vendor_id}")
    vendor_payments = books_client.vendor_payments.list_all(params={"vendor_id": vendor_id})
    
    parsed_withdrawals = []
    for tx in withdrawals:
        tx_id = tx.get("transaction_id") or tx.get("id")
        tx_date = parse_date(tx.get("date"))
        tx_amount = get_abs_amount(tx)
        ref = tx.get("reference_number") or tx.get("reference") or tx.get("cheque_number")
        parsed_withdrawals.append({
            "id": tx_id,
            "date": tx_date,
            "amount": tx_amount,
            "ref": ref,
            "raw": tx
        })
        
    parsed_payments = []
    for p in vendor_payments:
        p_id = p.get("payment_id") or p.get("id")
        p_date = parse_date(p.get("date"))
        try:
            p_amount = float(p.get("amount", 0.0))
        except (ValueError, TypeError):
            p_amount = 0.0
        ref = p.get("reference_number")
        parsed_payments.append({
            "id": p_id,
            "date": p_date,
            "amount": p_amount,
            "ref": ref,
            "raw": p
        })

    matched_bank_ids = set()
    matched_vendor_payment_ids = set()
    
    exact_matches = []
    strong_matches = []
    weak_matches = []
    
    # Pass 1: Exact Matches (Ref match + Exact Amount match + Date within tolerance)
    for tx in parsed_withdrawals:
        if not tx["date"] or not tx["id"]:
            continue
        for p in parsed_payments:
            if p["id"] in matched_vendor_payment_ids or not p["date"]:
                continue
            
            if not ref_match(tx["ref"], p["ref"]):
                continue
                
            amt_diff = abs(tx["amount"] - p["amount"])
            if amt_diff > 1e-9:
                continue
                
            date_diff = abs((tx["date"] - p["date"]).days)
            if date_diff <= date_tolerance_days:
                exact_matches.append((tx["raw"], p["raw"]))
                matched_bank_ids.add(tx["id"])
                matched_vendor_payment_ids.add(p["id"])
                break

    # Pass 2: Strong Matches (Amount matches exactly + Date within tolerance, no ref match required)
    for tx in parsed_withdrawals:
        if tx["id"] in matched_bank_ids or not tx["date"]:
            continue
        for p in parsed_payments:
            if p["id"] in matched_vendor_payment_ids or not p["date"]:
                continue
                
            amt_diff = abs(tx["amount"] - p["amount"])
            if amt_diff > 1e-9:
                continue
                
            date_diff = abs((tx["date"] - p["date"]).days)
            if date_diff <= date_tolerance_days:
                strong_matches.append((tx["raw"], p["raw"]))
                matched_bank_ids.add(tx["id"])
                matched_vendor_payment_ids.add(p["id"])
                break

    # Pass 3: Weak Matches (Amount matches within tolerance + Date within tolerance)
    if amount_tolerance > 0.0:
        for tx in parsed_withdrawals:
            if tx["id"] in matched_bank_ids or not tx["date"]:
                continue
            for p in parsed_payments:
                if p["id"] in matched_vendor_payment_ids or not p["date"]:
                    continue
                    
                amt_diff = abs(tx["amount"] - p["amount"])
                if amt_diff > amount_tolerance:
                    continue
                    
                date_diff = abs((tx["date"] - p["date"]).days)
                if date_diff <= date_tolerance_days:
                    weak_matches.append((tx["raw"], p["raw"]))
                    matched_bank_ids.add(tx["id"])
                    matched_vendor_payment_ids.add(p["id"])
                    break

    unmatched_bank = [tx["raw"] for tx in parsed_withdrawals if tx["id"] not in matched_bank_ids]
    unmatched_vendor = [p["raw"] for p in parsed_payments if p["id"] not in matched_vendor_payment_ids]
    
    return {
        "exact_matches": exact_matches,
        "strong_matches": strong_matches,
        "weak_matches": weak_matches,
        "unmatched_bank_transactions": unmatched_bank,
        "unmatched_vendor_payments": unmatched_vendor
    }

def match_bank_with_vendor_ledger(
    books_client: Any,
    bank_account_id: str,
    vendor_ledger_path: str,
    date_tolerance_days: int = 7,
    amount_tolerance: float = 0.0
) -> Dict[str, Any]:
    """
    Matches Bank Account transactions (money out/withdrawals) in Zoho Books with a cleaned
    external vendor ledger file (e.g. Polycab's ledger Excel file credits/receipts).
    """
    bank_txs = books_client.bank_transactions.list_all(params={"account_id": bank_account_id})
    
    withdrawals = []
    for tx in bank_txs:
        amount_val = 0.0
        try:
            amount_val = float(tx.get("amount", 0.0))
        except (ValueError, TypeError):
            pass
            
        is_withdrawal = False
        if amount_val < 0:
            is_withdrawal = True
        elif str(tx.get("debit_or_credit")).lower() == "debit":
            is_withdrawal = True
        elif str(tx.get("transaction_type")).lower() in ("expense", "withdrawal", "payment"):
            is_withdrawal = True
        elif str(tx.get("type")).lower() in ("expense", "withdrawal", "payment"):
            is_withdrawal = True
            
        if is_withdrawal:
            withdrawals.append(tx)
            
    ledger_entries = clean_ledger_file(vendor_ledger_path)
    ledger_receipts = [
        entry for entry in ledger_entries
        if entry.get("credit_amount", 0.0) > 0.0 or str(entry.get("document_type")).lower() == "receipt"
    ]
    
    parsed_withdrawals = []
    for tx in withdrawals:
        tx_id = tx.get("transaction_id") or tx.get("id")
        tx_date = parse_date(tx.get("date"))
        tx_amount = get_abs_amount(tx)
        ref = tx.get("reference_number") or tx.get("reference") or tx.get("cheque_number")
        parsed_withdrawals.append({
            "id": tx_id,
            "date": tx_date,
            "amount": tx_amount,
            "ref": ref,
            "raw": tx
        })
        
    parsed_receipts = []
    for r in ledger_receipts:
        r_id = r.get("transaction_no") or r.get("id")
        r_date = parse_date(r.get("date"))
        r_amount = r.get("credit_amount", 0.0)
        ref = r.get("transaction_reference") or r.get("transaction_no")
        parsed_receipts.append({
            "id": r_id,
            "date": r_date,
            "amount": r_amount,
            "ref": ref,
            "raw": r
        })

    matched_bank_ids = set()
    matched_receipt_ids = set()
    
    exact_matches = []
    strong_matches = []
    weak_matches = []

    # Pass 1: Exact Matches (Ref match + Exact Amount match + Date within tolerance)
    for tx in parsed_withdrawals:
        if not tx["date"] or not tx["id"]:
            continue
        for r in parsed_receipts:
            if r["id"] in matched_receipt_ids or not r["date"]:
                continue
            
            if not ref_match(tx["ref"], r["ref"]):
                continue
                
            amt_diff = abs(tx["amount"] - r["amount"])
            if amt_diff > 1e-9:
                continue
                
            date_diff = abs((tx["date"] - r["date"]).days)
            if date_diff <= date_tolerance_days:
                exact_matches.append((tx["raw"], r["raw"]))
                matched_bank_ids.add(tx["id"])
                matched_receipt_ids.add(r["id"])
                break

    # Pass 2: Strong Matches (Amount matches exactly + Date within tolerance, no ref match required)
    for tx in parsed_withdrawals:
        if tx["id"] in matched_bank_ids or not tx["date"]:
            continue
        for r in parsed_receipts:
            if r["id"] in matched_receipt_ids or not r["date"]:
                continue
                
            amt_diff = abs(tx["amount"] - r["amount"])
            if amt_diff > 1e-9:
                continue
                
            date_diff = abs((tx["date"] - r["date"]).days)
            if date_diff <= date_tolerance_days:
                strong_matches.append((tx["raw"], r["raw"]))
                matched_bank_ids.add(tx["id"])
                matched_receipt_ids.add(r["id"])
                break

    # Pass 3: Weak Matches (Amount matches within tolerance + Date within tolerance)
    if amount_tolerance > 0.0:
        for tx in parsed_withdrawals:
            if tx["id"] in matched_bank_ids or not tx["date"]:
                continue
            for r in parsed_receipts:
                if r["id"] in matched_receipt_ids or not r["date"]:
                    continue
                    
                amt_diff = abs(tx["amount"] - r["amount"])
                if amt_diff > amount_tolerance:
                    continue
                    
                date_diff = abs((tx["date"] - r["date"]).days)
                if date_diff <= date_tolerance_days:
                    weak_matches.append((tx["raw"], r["raw"]))
                    matched_bank_ids.add(tx["id"])
                    matched_receipt_ids.add(r["id"])
                    break

    unmatched_bank = [tx["raw"] for tx in parsed_withdrawals if tx["id"] not in matched_bank_ids]
    unmatched_receipts = [r["raw"] for r in parsed_receipts if r["id"] not in matched_receipt_ids]
    
    return {
        "exact_matches": exact_matches,
        "strong_matches": strong_matches,
        "weak_matches": weak_matches,
        "unmatched_bank_transactions": unmatched_bank,
        "unmatched_ledger_receipts": unmatched_receipts
    }

def fetch_vendor_credits(books_client: Any, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper to fetch all vendor credits across all pages using raw requests."""
    all_credits = []
    page = 1
    while True:
        current_params = {**params, 'page': page, 'per_page': 200}
        try:
            res = books_client.request('GET', 'vendorcredits', params=current_params)
            records = res.get('vendor_credits', res.get('vendorcredits', []))
            all_credits.extend(records)
            if not res.get('page_context', {}).get('has_more_page', False):
                break
            page += 1
        except Exception:
            break
    return all_credits

def check_credit_ref(vc: Dict[str, Any], l_cm: Dict[str, Any]) -> bool:
    vc_no = str(vc.get("vendor_credit_number") or "").strip().lower()
    vc_ref = str(vc.get("reference_number") or "").strip().lower()
    led_no = str(l_cm.get("transaction_no") or "").strip().lower()
    led_ref = str(l_cm.get("transaction_reference") or "").strip().lower()
    matches = []
    if led_no:
        matches.append(led_no == vc_no or led_no == vc_ref)
    if led_ref:
        matches.append(led_ref == vc_no or led_ref == vc_ref)
    return any(matches)

def check_bill_ref(b: Dict[str, Any], l_inv: Dict[str, Any]) -> bool:
    bill_no = str(b.get("bill_number") or "").strip().lower()
    bill_ref = str(b.get("reference_number") or "").strip().lower()
    led_no = str(l_inv.get("transaction_no") or "").strip().lower()
    led_ref = str(l_inv.get("transaction_reference") or "").strip().lower()
    matches = []
    if led_no:
        matches.append(led_no == bill_no or led_no == bill_ref)
    if led_ref:
        matches.append(led_ref == bill_no or led_ref == bill_ref)
    return any(matches)

def check_payment_ref(p: Dict[str, Any], l_rec: Dict[str, Any]) -> bool:
    pay_ref = str(p.get("reference_number") or "").strip().lower()
    led_no = str(l_rec.get("transaction_no") or "").strip().lower()
    led_ref = str(l_rec.get("transaction_reference") or "").strip().lower()
    matches = []
    if pay_ref:
        matches.append(pay_ref == led_no or pay_ref == led_ref)
    return any(matches)

def reconcile_document_group(
    books_entries: List[Dict[str, Any]],
    ledger_entries: List[Dict[str, Any]],
    books_id_fn: Any,
    books_date_fn: Any,
    books_amount_fn: Any,
    ledger_id_fn: Any,
    ledger_date_fn: Any,
    ledger_amount_fn: Any,
    ref_match_fn: Any,
    date_tolerance_days: int = 7,
    amount_tolerance: float = 0.0
) -> Dict[str, Any]:
    """Generic 3-pass reconciliation algorithm for a specific document group."""
    parsed_books = []
    for b in books_entries:
        b_id = books_id_fn(b)
        b_date = books_date_fn(b)
        b_amount = books_amount_fn(b)
        parsed_books.append({
            "id": b_id,
            "date": b_date,
            "amount": b_amount,
            "raw": b
        })

    parsed_ledger = []
    for l in ledger_entries:
        l_id = ledger_id_fn(l)
        l_date = ledger_date_fn(l)
        l_amount = ledger_amount_fn(l)
        parsed_ledger.append({
            "id": l_id,
            "date": l_date,
            "amount": l_amount,
            "raw": l
        })

    matched_books_ids = set()
    matched_ledger_ids = set()
    
    matches = []

    # Pass 1: Exact matches
    for b in parsed_books:
        if not b["date"] or not b["id"]:
            continue
        for l in parsed_ledger:
            if l["id"] in matched_ledger_ids or not l["date"]:
                continue
                
            if not ref_match_fn(b["raw"], l["raw"]):
                continue
                
            amt_diff = abs(b["amount"] - l["amount"])
            if amt_diff > 1e-9:
                continue
                
            date_diff = abs((b["date"] - l["date"]).days)
            if date_diff <= date_tolerance_days:
                matches.append((b["raw"], l["raw"]))
                matched_books_ids.add(b["id"])
                matched_ledger_ids.add(l["id"])
                break

    # Pass 2: Strong matches
    for b in parsed_books:
        if b["id"] in matched_books_ids or not b["date"]:
            continue
        for l in parsed_ledger:
            if l["id"] in matched_ledger_ids or not l["date"]:
                continue
                
            amt_diff = abs(b["amount"] - l["amount"])
            if amt_diff > 1e-9:
                continue
                
            date_diff = abs((b["date"] - l["date"]).days)
            if date_diff <= date_tolerance_days:
                matches.append((b["raw"], l["raw"]))
                matched_books_ids.add(b["id"])
                matched_ledger_ids.add(l["id"])
                break

    # Pass 3: Weak matches
    if amount_tolerance > 0.0:
        for b in parsed_books:
            if b["id"] in matched_books_ids or not b["date"]:
                continue
            for l in parsed_ledger:
                if l["id"] in matched_ledger_ids or not l["date"]:
                    continue
                    
                amt_diff = abs(b["amount"] - l["amount"])
                if amt_diff > amount_tolerance:
                    continue
                    
                date_diff = abs((b["date"] - l["date"]).days)
                if date_diff <= date_tolerance_days:
                    matches.append((b["raw"], l["raw"]))
                    matched_books_ids.add(b["id"])
                    matched_ledger_ids.add(l["id"])
                    break

    unmatched_books = [b["raw"] for b in parsed_books if b["id"] not in matched_books_ids]
    unmatched_ledger = [l["raw"] for l in parsed_ledger if l["id"] not in matched_ledger_ids]

    return {
        "matches": matches,
        "unmatched_books": unmatched_books,
        "unmatched_ledger": unmatched_ledger
    }

def reconcile_vendor_account(
    books_client: Any,
    vendor_id: str,
    vendor_ledger_path: str,
    date_tolerance_days: int = 7,
    amount_tolerance: float = 0.0
) -> Dict[str, Any]:
    """
    Reconciles Zoho Books Bills, Vendor Payments, and Vendor Credits against an external cleaned vendor ledger file.
    """
    metadata = get_ledger_metadata(vendor_ledger_path)
    start_date = parse_date(metadata.get("start_date"))
    end_date = parse_date(metadata.get("end_date"))

    ledger_entries = clean_ledger_file(vendor_ledger_path)
    
    if start_date and end_date:
        ledger_entries = [
            e for e in ledger_entries
            if e.get("date") and start_date <= parse_date(e["date"]) <= end_date
        ]
        
    ledger_sales_invoices = [
        e for e in ledger_entries
        if str(e.get("document_type") or "").strip().lower() == "sales invoice"
    ]
    ledger_receipts = [
        e for e in ledger_entries
        if str(e.get("document_type") or "").strip().lower() == "receipt"
    ]
    ledger_credit_memos = [
        e for e in ledger_entries
        if str(e.get("document_type") or "").strip().lower() == "credit memo"
    ]
    ledger_debit_memos = [
        e for e in ledger_entries
        if str(e.get("document_type") or "").strip().lower() == "debit memo"
    ]
    
    bill_params = {"vendor_id": vendor_id}
    if start_date and end_date:
        bill_params["from_date"] = start_date.strftime("%Y-%m-%d")
        bill_params["to_date"] = end_date.strftime("%Y-%m-%d")
    zoho_bills = books_client.bills.list_all(params=bill_params)
    
    if start_date and end_date:
        zoho_bills = [
            b for b in zoho_bills
            if b.get("date") and start_date <= parse_date(b["date"]) <= end_date
        ]
        
    books_sales_invoices = []
    books_debit_memos = []
    for b in zoho_bills:
        try:
            total_val = float(b.get("total") or b.get("amount") or 0.0)
        except (ValueError, TypeError):
            total_val = 0.0
            
        if total_val < 0.0:
            books_debit_memos.append(b)
        else:
            books_sales_invoices.append(b)
    
    payment_params = {"vendor_id": vendor_id}
    if start_date and end_date:
        payment_params["from_date"] = start_date.strftime("%Y-%m-%d")
        payment_params["to_date"] = end_date.strftime("%Y-%m-%d")
    zoho_payments = books_client.vendor_payments.list_all(params=payment_params)
    
    if start_date and end_date:
        zoho_payments = [
            p for p in zoho_payments
            if p.get("date") and start_date <= parse_date(p["date"]) <= end_date
        ]
        
    credit_params = {"vendor_id": vendor_id}
    if start_date and end_date:
        credit_params["from_date"] = start_date.strftime("%Y-%m-%d")
        credit_params["to_date"] = end_date.strftime("%Y-%m-%d")
    zoho_vendor_credits = fetch_vendor_credits(books_client, credit_params)
    
    if start_date and end_date:
        zoho_vendor_credits = [
            vc for vc in zoho_vendor_credits
            if vc.get("date") and start_date <= parse_date(vc["date"]) <= end_date
        ]

    sales_invoice_results = reconcile_document_group(
        books_entries=books_sales_invoices,
        ledger_entries=ledger_sales_invoices,
        books_id_fn=lambda b: b.get("bill_id") or b.get("id"),
        books_date_fn=lambda b: parse_date(b.get("date")),
        books_amount_fn=lambda b: float(b.get("total") or b.get("amount") or 0.0),
        ledger_id_fn=lambda l: l.get("transaction_no") or l.get("id"),
        ledger_date_fn=lambda l: parse_date(l.get("date")),
        ledger_amount_fn=lambda l: float(l.get("debit_amount") or 0.0),
        ref_match_fn=check_bill_ref,
        date_tolerance_days=date_tolerance_days,
        amount_tolerance=amount_tolerance
    )

    receipt_results = reconcile_document_group(
        books_entries=zoho_payments,
        ledger_entries=ledger_receipts,
        books_id_fn=lambda p: p.get("payment_id") or p.get("id"),
        books_date_fn=lambda p: parse_date(p.get("date")),
        books_amount_fn=lambda p: float(p.get("amount") or 0.0),
        ledger_id_fn=lambda l: l.get("transaction_no") or l.get("id"),
        ledger_date_fn=lambda l: parse_date(l.get("date")),
        ledger_amount_fn=lambda l: float(l.get("credit_amount") or 0.0),
        ref_match_fn=check_payment_ref,
        date_tolerance_days=date_tolerance_days,
        amount_tolerance=amount_tolerance
    )

    credit_memo_results = reconcile_document_group(
        books_entries=zoho_vendor_credits,
        ledger_entries=ledger_credit_memos,
        books_id_fn=lambda vc: vc.get("vendor_credit_id") or vc.get("id"),
        books_date_fn=lambda vc: parse_date(vc.get("date")),
        books_amount_fn=lambda vc: float(vc.get("total") or vc.get("amount") or 0.0),
        ledger_id_fn=lambda l: l.get("transaction_no") or l.get("id"),
        ledger_date_fn=lambda l: parse_date(l.get("date")),
        ledger_amount_fn=lambda l: float(l.get("credit_amount") or 0.0),
        ref_match_fn=check_credit_ref,
        date_tolerance_days=date_tolerance_days,
        amount_tolerance=amount_tolerance
    )

    debit_memo_results = reconcile_document_group(
        books_entries=books_debit_memos,
        ledger_entries=ledger_debit_memos,
        books_id_fn=lambda b: b.get("bill_id") or b.get("id"),
        books_date_fn=lambda b: parse_date(b.get("date")),
        books_amount_fn=lambda b: abs(float(b.get("total") or b.get("amount") or 0.0)),
        ledger_id_fn=lambda l: l.get("transaction_no") or l.get("id"),
        ledger_date_fn=lambda l: parse_date(l.get("date")),
        ledger_amount_fn=lambda l: float(l.get("debit_amount") or 0.0),
        ref_match_fn=check_bill_ref,
        date_tolerance_days=date_tolerance_days,
        amount_tolerance=amount_tolerance
    )

    return {
        "sales_invoice": sales_invoice_results,
        "receipt": receipt_results,
        "credit_memo": credit_memo_results,
        "debit_memo": debit_memo_results
    }
