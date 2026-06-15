import sys, os, csv, openpyxl
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
setup_logging()

GSTR_FILE        = "files/gst/gstr2b_reconciliation_consolidated.csv"
AMOUNT_TOLERANCE = 1.0  # ₹

GSTIN_TO_VENDOR_ID = dict(Config.GSTIN_TO_VENDOR_ID)


def amt(v):
    try:
        return round(float(str(v or 0).replace(",", "")), 2)
    except:
        return 0.0

def parse_date(s):
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date().isoformat()
    except:
        return s.strip()

# ── Load GSTR-2B ─────────────────────────────────────────────────────────────
print(f"Loading {GSTR_FILE} ...")
gst_rows = []
with open(GSTR_FILE, newline="", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        gst_rows.append({
            "gstin":         r["GSTIN of supplier"].strip(),
            "supplier":      r["Trade/Legal name"].strip(),
            "doc_type":      r["Document Type"].strip(),
            "doc_number":    r["Document Number"].strip(),
            "doc_date":      parse_date(r["Document Date"]),
            "doc_value":     amt(r["Document Value (₹)"]),
            "taxable_value": amt(r["Taxable Value (₹)"]),
            "igst":          amt(r["Integrated Tax(₹)"]),
            "cgst":          amt(r["Central Tax(₹)"]),
            "sgst":          amt(r["State/UT Tax(₹)"]),
            "itc":           r.get("ITC Availability","").strip(),
        })
invoices  = [g for g in gst_rows if g["doc_type"] != "Credit Note"]
cred_notes= [g for g in gst_rows if g["doc_type"] == "Credit Note"]
print(f"  {len(gst_rows)} rows  ({len(invoices)} invoices, {len(cred_notes)} credit notes)")

# ── Resolve unknown GSTINs ───────────────────────────────────────────────────
client = get_books_client()
for gstin, vid in GSTIN_TO_VENDOR_ID.items():
    if vid is None:
        res = client.request('GET', 'contacts', params={'search_text': gstin})
        c = res.get('contacts', [])
        GSTIN_TO_VENDOR_ID[gstin] = c[0]['contact_id'] if c else None
        if c:
            print(f"  Resolved {gstin} → {c[0]['contact_name']}")

# ── Download and parse GSTR-2 Inward Supplies report from Zoho Books ──────────
print("\nDownloading GSTR-2 Inward Supplies report from Zoho Books...")
temp_xlsx_path = "files/gst/inward_supplies_april_2025.xlsx"
client.gst.download_gstr_inward_supplies(
    save_path=temp_xlsx_path,
    params={
        "from_date": "2025-04-01",
        "to_date": "2025-04-30",
        "filter_by": "TransactionDate.CustomDate",
        "tax_settings_id": Config.ZOHO_TAX_SETTINGS_ID,
        "response_option": "1",
        "x-zb-source": "zbclient",
        "accept": "xlsx",
        "file_name": "Summary of Inward Supplies (GSTR-2)"
    }
)

actual_xlsx_path = temp_xlsx_path
if not os.path.isabs(actual_xlsx_path):
    out_path = os.path.abspath(os.path.join("output", temp_xlsx_path))
    if os.path.exists(out_path):
        actual_xlsx_path = out_path

print(f"Parsing GSTR-2 Inward Supplies report: {actual_xlsx_path} ...")
wb = openpyxl.load_workbook(actual_xlsx_path)

books_docs = {}
# Process B2B (Invoices) and DN (Credit/Debit Notes)
for sheet_name in ["b2b", "dn"]:
    if sheet_name not in wb.sheetnames:
        continue
    sheet = wb[sheet_name]
    for r in range(3, sheet.max_row + 1):
        doc_num = sheet.cell(r, 3).value
        if not doc_num:
            continue
        doc_num = str(doc_num).strip()
        
        vendor_name = str(sheet.cell(r, 2).value or "").strip()
        invoice_val = amt(sheet.cell(r, 5).value)
        taxable_val = amt(sheet.cell(r, 8).value)
        
        cgst = amt(sheet.cell(r, 11).value)
        sgst = amt(sheet.cell(r, 10).value)
        igst = amt(sheet.cell(r, 12).value)
        tax_val = cgst + sgst + igst
        
        if doc_num not in books_docs:
            books_docs[doc_num] = {
                "vendor_name": vendor_name,
                "sub_total": 0.0,
                "tax_total": 0.0,
                "total": invoice_val
            }
        books_docs[doc_num]["sub_total"] += taxable_val
        books_docs[doc_num]["tax_total"] += tax_val

# ── Process each row ─────────────────────────────────────────────────────────
matched_inv     = []
discrepant_inv  = []
missing_inv     = []
matched_cn      = []
discrepant_cn   = []
missing_cn      = []

print(f"\nMatching {len(gst_rows)} GSTR-2B documents against Zoho Books report data...")
for i, g in enumerate(gst_rows, 1):
    vendor_id = GSTIN_TO_VENDOR_ID.get(g["gstin"])
    is_cn     = g["doc_type"] == "Credit Note"

    if not vendor_id:
        (missing_cn if is_cn else missing_inv).append({"gst": g, "reason": "Vendor not mapped in Books"})
        continue

    # Look up document by number in our parsed Excel dictionary
    rec = books_docs.get(g["doc_number"])

    if not rec:
        (missing_cn if is_cn else missing_inv).append({"gst": g, "reason": "Not found in Zoho Books"})
        continue

    b_sub   = amt(rec.get("sub_total"))
    b_tax   = amt(rec.get("tax_total"))
    b_total = amt(rec.get("total"))
    # fallback: if sub_total still 0, approximate
    if b_sub == 0 and b_total > 0:
        b_sub = b_total - b_tax

    gst_tax  = round(g["igst"] + g["cgst"] + g["sgst"], 2)
    tv_diff  = round(b_sub - g["taxable_value"], 2)
    tax_diff = round(b_tax - gst_tax, 2)

    entry = {
        "gst":        g,
        "books":      rec,
        "b_sub":      b_sub,
        "b_tax":      b_tax,
        "b_total":    b_total,
        "gst_tax":    gst_tax,
        "tv_diff":    tv_diff,
        "tax_diff":   tax_diff,
    }

    bucket_ok  = matched_cn  if is_cn else matched_inv
    bucket_bad = discrepant_cn if is_cn else discrepant_inv

    if abs(tv_diff) <= AMOUNT_TOLERANCE:
        bucket_ok.append(entry)
    else:
        bucket_bad.append(entry)

# ── Report ────────────────────────────────────────────────────────────────────
S  = "=" * 84
D  = "─" * 84
f2 = lambda v, w=12: f"{v:>{w},.2f}"

print(f"\n{S}")
print(f"  GSTR-2B vs ZOHO BOOKS  |  April 2025  |  Tolerance ₹{AMOUNT_TOLERANCE}")
print(f"{S}")
print(f"  GSTR-2B rows : {len(gst_rows):4d}   Invoices: {len(invoices)}   Credit Notes: {len(cred_notes)}")

for label, ok, bad, miss in [
    ("INVOICES",      matched_inv,  discrepant_inv,  missing_inv),
    ("CREDIT NOTES",  matched_cn,   discrepant_cn,   missing_cn),
]:
    print(f"\n{D}\n  {label}\n{D}")
    print(f"  ✅ Fully matched       : {len(ok):4d}")
    print(f"  ⚠️  Amount discrepancy  : {len(bad):4d}")
    print(f"  ❌ Missing in Books    : {len(miss):4d}")

# ─ Missing ───────────────────────────────────────────────────────────────────
def show_missing(rows, title):
    if not rows: return
    print(f"\n{D}\n  {title}  ({len(rows)})\n{D}")
    print(f"  {'Supplier':<38} {'Doc Number':<28} {'Date':<12} {'Taxable':>12}  Reason")
    print(f"  {'-'*105}")
    for r in rows:
        g = r["gst"]
        print(f"  {g['supplier'][:37]:<38} {g['doc_number']:<28} {g['doc_date']:<12} {f2(g['taxable_value'])}  {r['reason']}")

show_missing(missing_inv, "❌ INVOICES IN GSTR-2B BUT NOT FOUND IN BOOKS")
show_missing(missing_cn,  "❌ CREDIT NOTES IN GSTR-2B BUT NOT FOUND IN BOOKS")

# ─ Discrepancies ─────────────────────────────────────────────────────────────
def show_discrepancy(rows, title):
    if not rows: return
    print(f"\n{D}\n  {title}  ({len(rows)})\n{D}")
    print(f"  {'Supplier':<32} {'Doc Number':<22} {'GST Taxable':>13} {'Books Taxable':>14} {'Diff':>9}  {'GST Tax':>9} {'Books Tax':>10} {'TaxDiff':>9}")
    print(f"  {'-'*125}")
    for e in sorted(rows, key=lambda x: abs(x["tv_diff"]), reverse=True):
        g = e["gst"]
        print(
            f"  {g['supplier'][:31]:<32} {g['doc_number']:<22}"
            f" {f2(g['taxable_value'],13)} {f2(e['b_sub'],14)} {e['tv_diff']:>+9.2f}"
            f"  {f2(g['igst']+g['cgst']+g['sgst'],9)} {f2(e['b_tax'],10)} {e['tax_diff']:>+9.2f}"
        )

show_discrepancy(discrepant_inv, "⚠️  INVOICES WITH TAXABLE VALUE DISCREPANCY")
show_discrepancy(discrepant_cn,  "⚠️  CREDIT NOTES WITH TAXABLE VALUE DISCREPANCY")

# ─ Totals ─────────────────────────────────────────────────────────────────────
all_ok  = matched_inv  + matched_cn
all_bad = discrepant_inv + discrepant_cn
all_miss= missing_inv  + missing_cn

gst_total_tv  = sum(g["taxable_value"] for g in gst_rows)
gst_total_tax = sum(g["igst"]+g["cgst"]+g["sgst"] for g in gst_rows)
ok_tv         = sum(e["gst"]["taxable_value"] for e in all_ok)
miss_tv       = sum(r["gst"]["taxable_value"] for r in all_miss)
disc_tv_net   = sum(e["tv_diff"] for e in all_bad)   # Books - GST

rate = len(all_ok) / len(gst_rows) * 100 if gst_rows else 0

print(f"\n{S}\n  FINANCIAL SUMMARY\n{S}")
print(f"  {'GSTR-2B total taxable value':<42}: ₹{gst_total_tv:>14,.2f}")
print(f"  {'GSTR-2B total tax (IGST+CGST+SGST)':<42}: ₹{gst_total_tax:>14,.2f}")
print(f"  {'Matched taxable (✅)':<42}: ₹{ok_tv:>14,.2f}")
print(f"  {'Missing from Books (❌ taxable)':<42}: ₹{miss_tv:>14,.2f}")
print(f"  {'Net diff on discrepant entries (Books−GST)':<42}: ₹{disc_tv_net:>+14,.2f}")
print(f"  {'Match rate':<42}: {rate:.1f}%  ({len(all_ok)}/{len(gst_rows)} rows)")
print(f"{S}\n")
