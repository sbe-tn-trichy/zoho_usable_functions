"""
Inspect vendor credit 2603189921 - fetch from Books and inspect source PDF.
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.core.config import Config
setup_logging()

client = get_books_client()

# 1. Find the VC by number
print("Searching for vendor credit 2603189921...")
res = client.request('GET', 'vendorcredits', params={
    'vendor_id': Config.POLYCAB_VENDOR_ID,
    'vendor_credit_number': '2603189921'
})
vcs = res.get('vendor_credits', [])

if not vcs:
    # try filter manually
    res2 = client.request('GET', 'vendorcredits', params={'vendor_id': Config.POLYCAB_VENDOR_ID, 'per_page': 200})
    vcs = [v for v in res2.get('vendor_credits', []) if v.get('vendor_credit_number') == '2603189921']

if not vcs:
    print("VC not found in list, trying direct search across pages...")
    page = 1
    while True:
        r = client.request('GET', 'vendorcredits', params={'vendor_id': Config.POLYCAB_VENDOR_ID, 'page': page, 'per_page': 200})
        records = r.get('vendor_credits', [])
        match = [v for v in records if v.get('vendor_credit_number') == '2603189921']
        if match:
            vcs = match
            break
        if not r.get('page_context', {}).get('has_more_page'):
            break
        page += 1

if not vcs:
    print("VC 2603189921 not found!")
    sys.exit(1)

vc = vcs[0]
vc_id = vc.get('vendor_credit_id')
print(f"\nFound VC:")
print(f"  ID     : {vc_id}")
print(f"  Number : {vc.get('vendor_credit_number')}")
print(f"  Date   : {vc.get('date')}")
print(f"  Amount : {vc.get('total')}")
print(f"  Status : {vc.get('status')}")

# 2. Get full detail to see line items
detail = client.request('GET', f'vendorcredits/{vc_id}')
vc_full = detail.get('vendor_credit', detail.get('vendorcredit', {}))
for li in vc_full.get('line_items', []):
    print(f"\n  Line Item:")
    print(f"    item_id      : {li.get('item_id')}")
    print(f"    name/sku     : {li.get('name')} / {li.get('sku')}")
    print(f"    description  : {li.get('description')}")
    print(f"    rate         : {li.get('rate')}")

# 3. Find source PDF
print(f"\n--- Checking source PDF ---")
import glob
cn_dir = Config.FILES_DIR
patterns = [
    os.path.join(cn_dir, f"*2603189921*.pdf"),
    os.path.join(cn_dir, f"CM-2603189921.pdf"),
    os.path.join(cn_dir, f"CN-2603189921.pdf"),
]
found_pdf = None
for p in patterns:
    matches = glob.glob(p)
    if matches:
        found_pdf = matches[0]
        break

if not found_pdf:
    print(f"PDF not found in {cn_dir}")
    # list all files to help
    if os.path.exists(cn_dir):
        files = [f for f in os.listdir(cn_dir) if '2603189921' in f]
        print(f"Files matching '2603189921': {files}")
else:
    print(f"PDF found: {found_pdf}")
    import pdfplumber
    with pdfplumber.open(found_pdf) as pdf:
        all_text = "\n".join([p.extract_text() or "" for p in pdf.pages])

    # Show RSO Number field
    print("\n--- Relevant PDF text lines ---")
    for line in all_text.split('\n'):
        if any(kw in line.lower() for kw in ['rso', 'return type', 'ldo01', 'llp01', 'ar invoice']):
            print(f"  >>> {line}")

    rso_match = re.search(r"RSO\s+(?:Number|No\.?)\s*:\s*(\S*)", all_text, re.IGNORECASE)
    print(f"\nRSO Number regex match: {rso_match.group(0) if rso_match else 'NOT FOUND'}")
    print(f"RSO Number value      : '{rso_match.group(1)}'" if rso_match else "  (no match)")

    # Show config item IDs for reference
    print(f"\nConfig.ZOHO_RSO_CN_ITEM_ID    = {Config.ZOHO_RSO_CN_ITEM_ID}")
    print(f"Config.ZOHO_SCHEME_CN_ITEM_ID = {Config.ZOHO_SCHEME_CN_ITEM_ID}")
