"""
Inspect both Zeiss vendor accounts to determine which one to use.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
setup_logging()

client = get_books_client()

ZEISS_IDS = [
    (Config.ZEISS_VENDOR_ID, "CARL ZEISS INDIA (BANGALORE) PVT LTD - #1"),
    ("1094368000021378870", "CARL ZEISS INDIA (BANGALORE) PVT LTD - #2"),
]

for vendor_id, label in ZEISS_IDS:
    print(f"\n{'='*60}")
    print(f"Vendor: {label}")
    print(f"ID    : {vendor_id}")

    # Fetch recent bills
    res_bills = client.request('GET', 'bills', params={'vendor_id': vendor_id, 'per_page': 5})
    bills = res_bills.get('bills', [])

    # Fetch recent VCs
    res_vcs = client.request('GET', 'vendorcredits', params={'vendor_id': vendor_id, 'per_page': 5})
    vcs = res_vcs.get('vendor_credits', [])

    # Fetch recent payments
    res_pmts = client.request('GET', 'vendorpayments', params={'vendor_id': vendor_id, 'per_page': 5})
    pmts = res_pmts.get('vendor_payments', [])

    print(f"  Bills   : {res_bills.get('page_context', {}).get('total', len(bills))} total")
    print(f"  Credits : {res_vcs.get('page_context', {}).get('total', len(vcs))} total")
    print(f"  Payments: {res_pmts.get('page_context', {}).get('total', len(pmts))} total")

    if bills:
        b = bills[0]
        print(f"  Latest Bill: {b.get('bill_number')} | {b.get('date')} | ₹{b.get('total')}")
