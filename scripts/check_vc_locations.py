"""
Check all Polycab vendor credits for any location other than Sri Bharath Electricals.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging

setup_logging()

EXPECTED_LOCATION_ID = Config.EXPECTED_LOCATION_ID
EXPECTED_LOCATION_NAME = Config.EXPECTED_LOCATION_NAME
VENDOR_ID = Config.POLYCAB_VENDOR_ID

client = get_books_client()

print(f"Fetching ALL vendor credits for Polycab (vendor_id={VENDOR_ID})...")

all_credits = []
page = 1
while True:
    res = client.request('GET', 'vendorcredits', params={
        'vendor_id': VENDOR_ID,
        'page': page,
        'per_page': 200
    })
    records = res.get('vendor_credits', res.get('vendorcredits', []))
    all_credits.extend(records)
    has_more = res.get('page_context', {}).get('has_more_page', False)
    print(f"  Page {page}: fetched {len(records)} credits (total so far: {len(all_credits)})")
    if not has_more:
        break
    page += 1

print(f"\nTotal vendor credits fetched: {len(all_credits)}")

# Filter those that do NOT match the expected location
mismatched = []
no_location = []

for vc in all_credits:
    loc_id = vc.get('location_id') or vc.get('branch_id') or ''
    loc_name = vc.get('location_name') or vc.get('branch_name') or ''
    vc_number = vc.get('vendor_credit_number', '')
    vc_id = vc.get('vendor_credit_id', '')
    date = vc.get('date', '')
    amount = vc.get('total', vc.get('amount', ''))
    status = vc.get('status', '')

    if not loc_id:
        no_location.append({
            'id': vc_id, 'number': vc_number, 'date': date,
            'amount': amount, 'status': status,
            'location_id': loc_id, 'location_name': loc_name
        })
    elif loc_id != EXPECTED_LOCATION_ID:
        mismatched.append({
            'id': vc_id, 'number': vc_number, 'date': date,
            'amount': amount, 'status': status,
            'location_id': loc_id, 'location_name': loc_name
        })

print(f"\n{'='*70}")
print(f"LOCATION CHECK RESULTS")
print(f"{'='*70}")
print(f"  Expected Location : {EXPECTED_LOCATION_NAME} (ID: {EXPECTED_LOCATION_ID})")
print(f"  Total VCs checked : {len(all_credits)}")
print(f"  Correctly located : {len(all_credits) - len(mismatched) - len(no_location)}")
print(f"  Wrong location    : {len(mismatched)}")
print(f"  No location set   : {len(no_location)}")

if mismatched:
    print(f"\n{'='*70}")
    print(f"VCs WITH WRONG LOCATION ({len(mismatched)}):")
    print(f"{'='*70}")
    print(f"  {'VC Number':<25} {'Date':<12} {'Amount':<14} {'Status':<10} {'Location Name':<25} {'Location ID'}")
    print(f"  {'-'*110}")
    for vc in mismatched:
        print(f"  {vc['number']:<25} {vc['date']:<12} {str(vc['amount']):<14} {vc['status']:<10} {vc['location_name']:<25} {vc['location_id']}")
else:
    print(f"\n✅ All {len(all_credits)} vendor credits have the correct location: {EXPECTED_LOCATION_NAME}")

if no_location:
    print(f"\n{'='*70}")
    print(f"VCs WITH NO LOCATION SET ({len(no_location)}):")
    print(f"{'='*70}")
    print(f"  {'VC Number':<25} {'Date':<12} {'Amount':<14} {'Status'}")
    print(f"  {'-'*70}")
    for vc in no_location:
        print(f"  {vc['number']:<25} {vc['date']:<12} {str(vc['amount']):<14} {vc['status']}")
