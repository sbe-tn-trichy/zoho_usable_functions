"""
Update vendor credit 2603189921 from RSO CN → Scheme CN item.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.logging_config import setup_logging
setup_logging()

VC_ID     = "1094368000056280329"
VC_NUMBER = "2603189921"

client = get_books_client()

# 1. Fetch full VC detail
print(f"Fetching VC {VC_NUMBER} (id={VC_ID})...")
detail = client.request('GET', f'vendorcredits/{VC_ID}')
vc = detail.get('vendor_credit', detail.get('vendorcredit', {}))

li = vc['line_items'][0]
print(f"  Current item_id  : {li['item_id']}  ({li.get('name') or li.get('sku')})")
print(f"  line_item_id     : {li['line_item_id']}")
print(f"  description      : {li.get('description')}")
print(f"  rate             : {li.get('rate')}")

# 2. Build update payload – swap item to Scheme CN
payload = {
    "vendor_id":            vc['vendor_id'],
    "vendor_credit_number": vc['vendor_credit_number'],
    "date":                 vc['date'],
    "line_items": [{
        "item_id":           Config.ZOHO_SCHEME_CN_ITEM_ID,   # ← Scheme CN
        "line_item_id":      li['line_item_id'],
        "rate":              li['rate'],
        "quantity":          li.get('quantity', 1),
        "description":       li.get('description', ''),
        "gst_treatment_code": li.get('gst_treatment_code', 'out_of_scope'),
    }]
}

if vc.get('location_id'):
    payload['location_id'] = vc['location_id']
    payload['branch_id']   = vc['location_id']

print(f"\nSending update payload:")
print(json.dumps(payload, indent=2))

# 3. PUT
res = client.request('PUT', f'vendorcredits/{VC_ID}', json=payload)
updated = res.get('vendor_credit', res.get('vendorcredit', {}))

new_li = (updated.get('line_items') or [{}])[0]
print(f"\n✅ Updated successfully!")
print(f"  New item_id  : {new_li.get('item_id')}")
print(f"  New name/sku : {new_li.get('name')} / {new_li.get('sku')}")
print(f"  Amount       : {updated.get('total')}")
print(f"  Status       : {updated.get('status')}")
