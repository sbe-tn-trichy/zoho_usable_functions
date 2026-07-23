from typing import List, Dict, Any, Optional, Union
from datetime import date, datetime

def normalize_phone_number(val: str) -> str:
    """
    Normalizes phone numbers to standard format '+91-XXXXXXXXXX':
    - Handles +91XXXXXXXXXX -> +91-XXXXXXXXXX
    - Handles 91XXXXXXXXXX -> +91-XXXXXXXXXX (if length 12)
    - Handles XXXXXXXXXX -> +91-XXXXXXXXXX (if starts with 6-9 and length 10)
    """
    if not val:
        return ""
    val_clean = str(val).strip().replace(" ", "").replace("-", "")
    if val_clean.startswith("+91"):
        digits = val_clean[3:]
    elif val_clean.startswith("91") and len(val_clean) == 12:
        digits = val_clean[2:]
    elif len(val_clean) == 10 and val_clean[0] in "6789":
        digits = val_clean
    else:
        return str(val).strip()
        
    if len(digits) == 10 and digits.isdigit():
        return f"+91-{digits}"
    return str(val).strip()

def fetch_active_customers(books_client: Any, normalize: bool = False) -> List[Dict[str, Any]]:
    """
    Fetches all active customer contacts from Zoho Books.
    Returns a list of customer dictionaries containing standard and custom fields.
    """
    contacts = books_client.contacts.list_all(params={"status": "active"})
    customers = [c for c in contacts if c.get("contact_type") == "customer"]
    
    records = []
    for c in customers:
        phone_val = c.get("phone")
        mobile_val = c.get("mobile")
        
        if normalize:
            phone_val = normalize_phone_number(phone_val)
            mobile_val = normalize_phone_number(mobile_val)
            
        records.append({
            "contact_id": c.get("contact_id"),
            "contact_number": c.get("contact_number"),
            "contact_name": c.get("contact_name"),
            "company_name": c.get("company_name"),
            "status": c.get("status"),
            "phone": phone_val,
            "mobile": mobile_val,
            "email": c.get("email"),
            "gst_no": c.get("gst_no"),
            "pan_no": c.get("pan_no"),
            "place_of_contact": c.get("place_of_contact"),
            "place_of_contact_formatted": c.get("place_of_contact_formatted"),
            "outstanding_receivable_amount": c.get("outstanding_receivable_amount"),
            "unused_credits_receivable_amount": c.get("unused_credits_receivable_amount"),
            "cf_district": c.get("cf_district"),
            "cf_b_name": c.get("cf_b_name"),
            "cf_jurisdiction": c.get("cf_jurisdiction")
        })
    return records


def _to_float(value: Any) -> float:
    """Best-effort conversion for Zoho numeric fields returned as strings or None."""
    if value in (None, "", "nan"):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def find_customers_with_unused_credits(
    books_client: Any,
    normalize: bool = False,
    min_unused_credit_amount: float = 0.0,
) -> Dict[str, Any]:
    """
    Finds active customers that have unused credit balance in Zoho Books.

    Returns:
        {
            "customers": [
                {
                    "contact_id": "...",
                    "contact_name": "...",
                    "company_name": "...",
                    "unused_credits_receivable_amount": 123.45,
                    ...
                }
            ],
            "summary": {
                "total_customers_checked": int,
                "customers_with_unused_credits": int,
                "total_unused_credit_amount": float
            }
        }
    """
    customers = fetch_active_customers(books_client, normalize=normalize)

    matches: List[Dict[str, Any]] = []
    total_unused_credit_amount = 0.0

    for customer in customers:
        unused_credit_amount = _to_float(customer.get("unused_credits_receivable_amount"))
        if unused_credit_amount <= min_unused_credit_amount:
            continue

        total_unused_credit_amount += unused_credit_amount
        matches.append({
            "contact_id": customer.get("contact_id"),
            "contact_number": customer.get("contact_number"),
            "contact_name": customer.get("contact_name"),
            "company_name": customer.get("company_name"),
            "status": customer.get("status"),
            "phone": customer.get("phone"),
            "mobile": customer.get("mobile"),
            "email": customer.get("email"),
            "gst_no": customer.get("gst_no"),
            "pan_no": customer.get("pan_no"),
            "place_of_contact": customer.get("place_of_contact"),
            "place_of_contact_formatted": customer.get("place_of_contact_formatted"),
            "outstanding_receivable_amount": _to_float(customer.get("outstanding_receivable_amount")),
            "unused_credits_receivable_amount": unused_credit_amount,
            "cf_district": customer.get("cf_district"),
            "cf_b_name": customer.get("cf_b_name"),
            "cf_jurisdiction": customer.get("cf_jurisdiction"),
        })

    matches.sort(
        key=lambda row: (
            -(row["unused_credits_receivable_amount"] or 0.0),
            (row["contact_name"] or "").lower(),
            (row["contact_id"] or ""),
        )
    )

    return {
        "customers": matches,
        "summary": {
            "total_customers_checked": len(customers),
            "customers_with_unused_credits": len(matches),
            "total_unused_credit_amount": round(total_unused_credit_amount, 2),
        },
    }

def find_same_day_payment_anomalies(
    books_client: Any,
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Finds anomalies where a single customer has more than one payment entry on the same day.
    
    Parameters:
        books_client: ZohoBooksAPI client instance
        start_date: Optional start date filter (str 'YYYY-MM-DD', date or datetime)
        end_date: Optional end date filter (str 'YYYY-MM-DD', date or datetime)
        customer_id: Optional customer ID to filter by
        
    Returns:
        A dictionary containing the anomalies grouped by customer and date:
        {
            "anomalies": [
                {
                    "customer_id": "...",
                    "customer_name": "...",
                    "date": "2026-07-06",
                    "payment_count": 2,
                    "payments": [
                        {
                            "payment_id": "...",
                            "payment_number": "...",
                            "amount": 100.0,
                            "payment_mode": "...",
                            "reference_number": "..."
                        },
                        ...
                    ]
                },
                ...
            ],
            "summary": {
                "total_payments_checked": int,
                "total_anomalies_found": int
            }
        }
    """
    params = {}
    
    # Helper to convert dates to string format
    def format_dt(dt):
        if isinstance(dt, (date, datetime)):
            return dt.strftime("%Y-%m-%d")
        return dt
        
    s_date = format_dt(start_date)
    e_date = format_dt(end_date)
    
    if s_date:
        params["date_start"] = s_date
    if e_date:
        params["date_end"] = e_date
    if customer_id:
        params["customer_id"] = customer_id

    # Fetch customer payments
    payments = books_client.customer_payments.list_all(params=params)

    # Group by customer_id and date
    from collections import defaultdict
    grouped = defaultdict(list)
    for p in payments:
        cust_id = p.get("customer_id")
        p_date = p.get("date")
        if cust_id and p_date:
            grouped[(cust_id, p_date)].append(p)

    # Find groups with > 1 entry
    anomalies = []
    for (cust_id, p_date), p_list in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        if len(p_list) > 1:
            cust_name = p_list[0].get("customer_name") or ""
            payments_details = []
            for p in p_list:
                payments_details.append({
                    "payment_id": p.get("payment_id"),
                    "payment_number": p.get("payment_number"),
                    "amount": float(p.get("amount") or 0.0),
                    "payment_mode": p.get("payment_mode") or "",
                    "reference_number": p.get("reference_number") or ""
                })
            anomalies.append({
                "customer_id": cust_id,
                "customer_name": cust_name,
                "date": p_date,
                "payment_count": len(p_list),
                "payments": payments_details
            })

    return {
        "anomalies": anomalies,
        "summary": {
            "total_payments_checked": len(payments),
            "total_anomalies_found": len(anomalies)
        }
    }
