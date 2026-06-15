"""
Quick diagnostic: fetch one Zeiss bill and print all its amount fields.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
import json
setup_logging()

client = get_books_client()

# Fetch a known Zeiss invoice from GSTR-2B
VENDOR_ID  = Config.ZEISS_VENDOR_ID
BILL_NUM   = "VDO2925012476"   # first invoice in GSTR-2B

# List endpoint
res = client.request('GET', 'bills', params={'vendor_id': VENDOR_ID, 'bill_number': BILL_NUM})
bills = res.get('bills', [])
if not bills:
    print("Not found via list"); exit()

bill_list = bills[0]
bill_id   = bill_list.get('bill_id')
print("=== LIST endpoint fields ===")
for k in ['bill_id','bill_number','date','total','sub_total','tax_total','tax_amount','balance','amount']:
    print(f"  {k:20}: {bill_list.get(k)}")

# Detail endpoint
res2  = client.request('GET', f'bills/{bill_id}')
bill_detail = res2.get('bill', {})
print("\n=== DETAIL endpoint fields ===")
for k in ['bill_id','bill_number','date','total','sub_total','tax_total','tax_amount','balance','amount']:
    print(f"  {k:20}: {bill_detail.get(k)}")

print(f"\nGSTR-2B taxable for VDO2925012476 : 200.0 (IGST=36.0)")
print(f"Books sub_total                    : {bill_list.get('sub_total')}")
print(f"Books total                        : {bill_list.get('total')}")
