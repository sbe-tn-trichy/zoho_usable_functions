import sys
import os
import argparse
import glob
import shutil
from datetime import datetime

# Inject src directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from zoho_usable_functions.core.config import Config
from zoho_usable_functions.core.auth import get_books_client
from zoho_usable_functions.core.logging_config import setup_logging
from zoho_usable_functions.reconciliation.gstr2b import reconcile_gstr2b_with_books, clean_gstr2b_xlsx

# Helper to format amounts for printing
f2 = lambda v, w=12: f"{v:>{w},.2f}"
S  = "=" * 84
D  = "─" * 84

def show_missing(rows, title):
    if not rows:
        return
    print(f"\n{D}\n  {title}  ({len(rows)})\n{D}")
    print(f"  {'Supplier':<38} {'Doc Number':<28} {'Date':<12} {'Taxable':>12}  Reason")
    print(f"  {'-'*105}")
    for r in rows:
        g = r["gst"]
        print(f"  {g['supplier'][:37]:<38} {g['doc_number']:<28} {g['doc_date']:<12} {f2(g['taxable_value'])}  {r['reason']}")

def show_discrepancy(rows, title):
    if not rows:
        return
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

def main():
    parser = argparse.ArgumentParser(description="Reconcile GSTR-2B CSV/XLSX with Zoho Books inward supplies.")
    parser.add_argument("--gstr-path", default="input_files/gst", help="Path to GSTR-2B file, folder, or XLSX file")
    parser.add_argument("--tolerance", type=float, default=1.0, help="Amount tolerance in ₹")
    parser.add_argument("--from-date", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--temp-xlsx", default=None, help="Temp path to save Zoho report")
    args = parser.parse_args()

    setup_logging()

    # Pre-process XLSX files if directory or XLSX file is specified
    gstr_path = args.gstr_path
    processed_dir = None
    files_to_move = []

    if os.path.isdir(gstr_path):
        processed_dir = os.path.join(gstr_path, "processed_files")
        xlsx_files = glob.glob(os.path.join(gstr_path, "*.xlsx"))
        for xlsx_file in xlsx_files:
            csv_name = os.path.splitext(os.path.basename(xlsx_file))[0] + ".csv"
            csv_path = os.path.join(gstr_path, csv_name)
            print(f"Cleaning Excel file: {xlsx_file} -> {csv_path}")
            try:
                clean_gstr2b_xlsx(xlsx_file, csv_path)
                files_to_move.append(xlsx_file)
                files_to_move.append(csv_path)
            except Exception as e:
                print(f"Failed to clean Excel file {xlsx_file}: {e}")
                sys.exit(1)
    elif gstr_path.endswith(".xlsx") and os.path.isfile(gstr_path):
        # Handle case where user directly passes an XLSX file path
        parent_dir = os.path.dirname(gstr_path) or "."
        processed_dir = os.path.join(parent_dir, "processed_files")
        csv_name = os.path.splitext(os.path.basename(gstr_path))[0] + ".csv"
        csv_path = os.path.join(parent_dir, csv_name)
        print(f"Cleaning Excel file: {gstr_path} -> {csv_path}")
        try:
            clean_gstr2b_xlsx(gstr_path, csv_path)
            files_to_move.append(gstr_path)
            files_to_move.append(csv_path)
            gstr_path = csv_path # Reconcile using the generated CSV
        except Exception as e:
            print(f"Failed to clean Excel file {gstr_path}: {e}")
            sys.exit(1)
    elif gstr_path.endswith(".csv") and os.path.isfile(gstr_path):
        # Keep track of the CSV file if passed directly so it gets moved
        parent_dir = os.path.dirname(gstr_path) or "."
        processed_dir = os.path.join(parent_dir, "processed_files")
        files_to_move.append(gstr_path)

    try:
        books_client = get_books_client()
    except Exception as e:
        print(f"Error: Could not initialize Zoho Books client: {e}")
        sys.exit(1)

    print(f"Starting GSTR-2B reconciliation using path: {gstr_path}...")
    
    try:
        results = reconcile_gstr2b_with_books(
            books_client=books_client,
            gstr2b_csv_path=gstr_path,
            from_date=args.from_date,
            to_date=args.to_date,
            amount_tolerance=args.tolerance,
            temp_xlsx_path=args.temp_xlsx
        )
    except Exception as e:
        print(f"Reconciliation failed with error: {e}")
        sys.exit(1)

    # Print Report
    print(f"\n{S}")
    print(f"  GSTR-2B vs ZOHO BOOKS  |  Date Range: {args.from_date} to {args.to_date}  |  Tolerance ₹{args.tolerance}")
    print(f"{S}")
    print(f"  GSTR-2B rows : {results['gst_rows_count']:4d}   Invoices: {results['invoices_count']}   Credit Notes: {results['credits_count']}")

    print(f"\n{D}\n  INVOICES\n{D}")
    print(f"  ✅ Fully matched       : {len(results['matched_invoices']):4d}")
    print(f"  ⚠️  Amount discrepancy  : {len(results['discrepant_invoices']):4d}")
    print(f"  ❌ Missing in Books    : {len(results['missing_invoices']):4d}")

    print(f"\n{D}\n  CREDIT NOTES\n{D}")
    print(f"  ✅ Fully matched       : {len(results['matched_credits']):4d}")
    print(f"  ⚠️  Amount discrepancy  : {len(results['discrepant_credits']):4d}")
    print(f"  ❌ Missing in Books    : {len(results['missing_credits']):4d}")

    show_missing(results['missing_invoices'], "❌ INVOICES IN GSTR-2B BUT NOT FOUND IN BOOKS")
    show_missing(results['missing_credits'],  "❌ CREDIT NOTES IN GSTR-2B BUT NOT FOUND IN BOOKS")

    show_discrepancy(results['discrepant_invoices'], "⚠️  INVOICES WITH TAXABLE VALUE DISCREPANCY")
    show_discrepancy(results['discrepant_credits'],  "⚠️  CREDIT NOTES WITH TAXABLE VALUE DISCREPANCY")

    # Totals
    all_ok = results['matched_invoices'] + results['matched_credits']
    all_bad = results['discrepant_invoices'] + results['discrepant_credits']
    all_miss = results['missing_invoices'] + results['missing_credits']

    gst_total_tv = (
        sum(e["gst"]["taxable_value"] for e in all_ok) +
        sum(e["gst"]["taxable_value"] for e in all_bad) +
        sum(r["gst"]["taxable_value"] for r in all_miss)
    )
    gst_total_tax = (
        sum(e["gst"]["igst"] + e["gst"]["cgst"] + e["gst"]["sgst"] for e in all_ok) +
        sum(e["gst"]["igst"] + e["gst"]["cgst"] + e["gst"]["sgst"] for e in all_bad) +
        sum(r["gst"]["igst"] + r["gst"]["cgst"] + r["gst"]["sgst"] for r in all_miss)
    )
    ok_tv = sum(e["gst"]["taxable_value"] for e in all_ok)
    miss_tv = sum(r["gst"]["taxable_value"] for r in all_miss)
    disc_tv_net = sum(e["tv_diff"] for e in all_bad)

    total_rows = results['gst_rows_count']
    rate = len(all_ok) / total_rows * 100 if total_rows else 0

    print(f"\n{S}\n  FINANCIAL SUMMARY\n{S}")
    print(f"  {'GSTR-2B total taxable value':<42}: ₹{gst_total_tv:>14,.2f}")
    print(f"  {'GSTR-2B total tax (IGST+CGST+SGST)':<42}: ₹{gst_total_tax:>14,.2f}")
    print(f"  {'Matched taxable (✅)':<42}: ₹{ok_tv:>14,.2f}")
    print(f"  {'Missing from Books (❌ taxable)':<42}: ₹{miss_tv:>14,.2f}")
    print(f"  {'Net diff on discrepant entries (Books−GST)':<42}: ₹{disc_tv_net:>+14,.2f}")
    print(f"  {'Match rate':<42}: {rate:.1f}%  ({len(all_ok)}/{total_rows} rows)")
    print(f"{S}\n")

    # Move processed files to processed_files/ folder
    if processed_dir and files_to_move:
        os.makedirs(processed_dir, exist_ok=True)
        for f in files_to_move:
            if os.path.exists(f):
                dest = os.path.join(processed_dir, os.path.basename(f))
                print(f"Moving processed file: {f} -> {dest}")
                shutil.move(f, dest)

if __name__ == "__main__":
    main()
