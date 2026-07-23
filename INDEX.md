# zoho_usable_functions — Code Index

> **PROJECT SPLIT**: Confirmed reconciliation and credit-memo modules have been
> promoted to the sibling `zoho_sdk_advanced` project. This repository is the
> trial/incubation project. Compatibility copies remain temporarily so existing
> scripts do not break during migration.

> **AI AGENT INSTRUCTION**: Read this file first before opening any source file.
> It maps the entire codebase. Only open source files when you need implementation details beyond what is here.

---

## Project Purpose

High-level Python helper library + scripts built on top of `zoho_sdk`.
Main domains:
1. **Reconciliation** — Match Zoho Books records against external vendor/bank ledger files
2. **Credit Memos** — Parse Polycab PDF credit notes and post them to Zoho Books
3. **Inventory** — Compare FAN stock SKUs with Zoho Inventory and prepare/create missing items

---

## Directory Layout

```
zoho_usable_functions/
├── src/zoho_usable_functions/       # Installable library (pip install -e .)
│   ├── __init__.py                  # Public API — re-exports all public functions
│   ├── core/
│   │   ├── config.py                # Config class — all env vars with defaults
│   │   ├── auth.py                  # Zoho API client factory functions
│   │   └── logging_config.py        # Logger setup
│   ├── reconciliation/
│   │   ├── _utils.py                # Shared helpers: parse_date, get_abs_amount, ref_match
│   │   ├── _bank_matcher.py         # Bank statement ↔ Zoho Books matching
│   │   ├── _vendor_reconciler.py    # 4-way vendor-account reconciliation engine
│   │   ├── cleaner.py               # Parse raw vendor ledger files → normalised dicts
│   │   ├── gstr2b.py                # GSTR-2B reconciliation module
│   │   ├── matcher.py               # Re-export facade (public API unchanged)
│   │   └── zeiss_pdf.py             # Carl Zeiss PDF statements parser and consolidator
│   ├── credit_memos/
│   │   └── processor.py             # Parse Polycab PDFs, batch processing, location auditor
│   └── inventory/
│       ├── item_sync.py             # Generic Zoho Inventory item fetch/diff/payload/create helpers
│       └── fan_item_sync.py         # FAN stock Excel ↔ Zoho Inventory item sync adapter
├── scripts/                         # Standalone runner scripts (not importable library)
│   ├── reconciliation/
│   │   ├── convert_zeiss_pdf.py     # Convert Zeiss PDF statements → CSV and consolidate
│   │   ├── reconcile_bank.py        # Bank account ↔ vendor ledger reconciliation
│   │   ├── reconcile_vendor.py      # Vendor account full reconciliation (Polycab)
│   │   ├── reconcile_zeiss.py       # Vendor account full reconciliation (Zeiss)
│   │   └── run_reconciliation.py    # Generic reconciliation entry point
│   ├── reconcile_gstr2b.py          # GSTR-2B reconciliation (standalone)
│   ├── export_fan_purchase_items.py # Export and categorize fan purchase items to CSV
│   ├── propose_groups.py            # Propose group assignments for active items without group
│   ├── inventory/                   # Zoho Inventory helper scripts
│   ├── books/                       # Zoho Books helper scripts
│   ├── payment_reconciliation/      # Payment reconciliation helper scripts
│   ├── update_sku_units.py          # Update SKU units in Zoho
│   └── credit_memos/                # Credit memo processing scripts
├── input_files/                           # Input data files (ledgers, PDFs) — gitignored
│   ├── polycab/ledger/              # Polycab Excel ledger files (.xls)
│   ├── polycab/cn/                  # Polycab Credit Note PDFs
│   └── zeiss/                       # Zeiss CSV ledger files
├── logs/                            # Runtime logs
├── output/                          # Reconciliation output files
└── tests/                           # Pytest tests
```

---

## Public API (`from zoho_usable_functions import ...`)

All exports are declared in `src/zoho_usable_functions/__init__.py`.

### reconciliation.cleaner

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `get_ledger_metadata` | `(file_path: str)` | `Dict` | Extracts date range + party info from a ledger file. Auto-detects Polycab (.xls) vs Zeiss (.csv). Keys: `start_date`, `end_date`, `party_name`, `opening_balance` |
| `clean_ledger_file` | `(file_path: str, vendor_key: Optional[str] = None)` | `List[Dict]` | Parses and normalises a vendor ledger. Auto-detects vendor from filename if `vendor_key` omitted. Supported `vendor_key`: `"polycab"`, `"zeiss"`. Adds `"id"` field to each entry. |

**Ledger entry dict shape** (output of `clean_ledger_file`):
```python
{
    "id": "polycab_0",           # auto-added index key
    "date": "2026-01-15",        # ISO format
    "document_type": "sales invoice" | "receipt" | "credit memo" | "debit memo",
    "transaction_no": "...",
    "transaction_reference": "...",
    "debit_amount": 0.0,
    "credit_amount": 0.0,
    # Polycab only:
    "account_no": "...", "account_name": "...", "customer_po_no": "...", "closing_balance": 0.0
}
```

**Auto-detect rules** (`clean_ledger_file` / `get_ledger_metadata`):
- Filename starts with `277498` or contains `polycab` → `vendor_key = "polycab"` (.xls)
- Filename contains `zeiss` → `vendor_key = "zeiss"` (.csv, columns: `Posting Date`, `Document No`, `Invoice Number`, `Voucher Type`, `Debit`, `Credit`)

---

### reconciliation.matcher

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `match_ledger_entries` | `(books_client, bank_account_id, vendor_id, date_tolerance_days=7, amount_tolerance=0.0, start_date=None, end_date=None)` | `Dict` | Bank withdrawals ↔ Zoho vendor payments. Fetches both sides from Zoho Books API. |
| `match_bank_with_vendor_ledger` | `(books_client, bank_account_id, vendor_ledger_path, date_tolerance_days=7, amount_tolerance=0.0)` | `Dict` | Bank withdrawals (Zoho Books) ↔ vendor ledger receipts (local file). Date range auto-inferred from ledger. |
| `reconcile_vendor_account` | `(books_client, vendor_id, vendor_ledger_path, date_tolerance_days=7, amount_tolerance=0.0)` | `Dict` | Full 4-way reconciliation: Bills, Payments, Vendor Credits, Debit Memos vs ledger. |
| `reconcile_vendor` | `(vendor_ledger_path, vendor_id=None, date_tolerance_days=7, amount_tolerance=0.0, books_client=None)` | `Dict` | High-level wrapper that auto-initializes the Books client and auto-detects vendor from ledger path if omitted. |

**3-pass matching algorithm** (used in all matcher functions):
1. Pass 1 — **Exact**: ref match + exact amount + date within tolerance
2. Pass 2 — **Strong**: exact amount + date within tolerance (no ref required)
3. Pass 3 — **Weak**: amount within `amount_tolerance` + date within tolerance (only if `amount_tolerance > 0`)

**Return dict shape** for `match_ledger_entries` / `match_bank_with_vendor_ledger`:
```python
{
    "exact_matches": [(bank_tx_dict, payment_dict), ...],
    "strong_matches": [...],
    "weak_matches": [...],
    "unmatched_bank_transactions": [bank_tx_dict, ...],
    "unmatched_vendor_payments": [payment_dict, ...],   # match_ledger_entries only
    "unmatched_ledger_receipts": [ledger_dict, ...],    # match_bank_with_vendor_ledger only
}
```

**Return dict shape** for `reconcile_vendor_account`:
```python
{
    "sales_invoice": {"matches": [...], "unmatched_books": [...], "unmatched_ledger": [...]},
    "receipt":       {"matches": [...], "unmatched_books": [...], "unmatched_ledger": [...]},
    "credit_memo":   {"matches": [...], "unmatched_books": [...], "unmatched_ledger": [...]},
    "debit_memo":    {"matches": [...], "unmatched_books": [...], "unmatched_ledger": [...]},
}
```
---

### reconciliation.gstr2b

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `reconcile_gstr2b_with_books` | `(books_client=None, gstr2b_csv_path="input_files/gst", from_date=None, to_date=None, amount_tolerance=1.0, temp_xlsx_path=None)` | `Dict` | Full reconciliation between GSTR-2B CSV (or directory containing CSVs) and Zoho Books inward supplies. Auto-initializes auth. |

**Return dict shape** for `reconcile_gstr2b_with_books`:
```python
{
    "matched_invoices": [...],
    "discrepant_invoices": [...],
    "missing_invoices": [...],
    "matched_credits": [...],
    "discrepant_credits": [...],
    "missing_credits": [...],
    "gst_rows_count": int,
    "invoices_count": int,
    "credits_count": int,
    "gstin_to_vendor_id": dict
}
```

---

### reconciliation.zeiss_pdf

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `parse_zeiss_pdf_statement` | `(pdf_path: str)` | `List[Dict]` | Parses transaction lines from a Zeiss PDF statement using `pdfplumber`. |
| `consolidate_zeiss_statements` | `(ledgers_dir: str, output_csv_path: str)` | `List[Dict]` | Parses, de-duplicates, sorts chronologically, and saves Carl Zeiss PDF statements to CSV. |

---

### reconciliation.stock

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `find_negative_stock_items` | `(books_client, location_name="SBE", purchase_account_id=None)` | `List[Dict]` | Finds all items with negative accounting stock in the specified location, optionally filtered by purchase account ID. |

---

### credit_memos.processor

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `parse_polycab_credit_memo` | `(pdf_path: str)` | `Dict` | Extracts CN number, date, amount, description from Polycab PDF. Uses `pdfplumber`. |
| `create_vendor_credit_from_pdf` | `(books_client, pdf_path, vendor_name="Polycab", account_name="Polycab Scheme - Expense")` | `Dict` | Parses PDF → classifies RSO/Scheme → POSTs vendor credit to Zoho Books. |
| `upload_vendor_credit_attachment` | `(books_client, vendor_credit_id: str, pdf_path: str)` | `Dict` | Compatibility wrapper over the SDK Vendor Credits attachment action. |
| `upload_to_workdrive` | `(wd_client, folder_id: str, pdf_path: str)` | `Dict` | Uploads PDF to Zoho WorkDrive folder. |
| `process_polycab_credit_memos` | `(books_client=None, wd_client=None, files_dir=None, folder_id=None, vendor_id=None)` | `Dict` | Batch process Polycab credit memo PDFs with auto-authentication/initialization. |
| `check_vendor_credits_location` | `(books_client=None, vendor_id=None, expected_location_id=None)` | `Dict` | Audits all vendor credits for correct/mismatched/unset location settings. Auto-initializes. |

**`parse_polycab_credit_memo` return dict**:
```python
{
    "vendor_name": "Polycab India Limited",
    "vendor_credit_number": "12345678",   # AR Invoice Number from PDF
    "date": "2026-01-15",                 # YYYY-MM-DD
    "amount": 10000.0,
    "description": "...",
    "raw_text": "..."                      # Full PDF text for downstream logic
}
```

**CN Classification** (`resolve_item_id`):
- If PDF contains `RSO Number : <digits>` → RSO CN → uses `Config.ZOHO_RSO_CN_ITEM_ID`
- Otherwise → Scheme CN → uses `Config.ZOHO_SCHEME_CN_ITEM_ID`

---

### inventory.item_sync / inventory.fan_item_sync

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `fetch_items_for_purchase_account` | `(client, purchase_account_id, status="all")` | `List[Dict]` | Compatibility wrapper over `client.items.list_by_purchase_account`. |
| `fetch_inventory_items` | `(client, purchase_account_id=None, max_pages=None, verbose=False)` | `List[Dict]` | Generic SDK-backed fetch with optional bounded pagination for previews/test runs. |
| `items_to_frame` | `(items, match_key="sku")` | `pandas.DataFrame` | Normalises SDK item records into a tabular frame with `MATCH_KEY` / `SKU_KEY`. |
| `find_item_diff` | `(target_rows, existing_items, match_key="sku", compare_fields=None)` | `Dict` | Classifies target rows into missing, changed, unchanged, duplicate/blocking. Changed items are report-only in v1. |
| `compare_items_with_inventory` | `(candidates, output_dir, *, client=None, client_factory=None, existing_items_file=None, ...)` | `Dict` | Reusable orchestration for snapshot/API loading, comparison, and report generation. |
| `write_item_diff_outputs` | `(diff, output_dir, filename_prefix=..., report_label=..., filenames=None)` | `Dict[str, Path]` | Writes configurable missing/changed CSV and XLSX reports plus an Inventory snapshot. |
| `build_inventory_item_payload` | `(row, defaults=None, tax_preferences=None)` | `(payload, issues)` | Generic Zoho Inventory item create-payload builder. |
| `prepare_item_create_payloads` | `(rows, output_dir, payload_builder=..., filename_prefix=..., filename_suffix="")` | `Dict` | Writes create payload preview JSON/CSV and validation XLSX. |
| `prepare_inventory_items_from_sheet` | `(create_xlsx, output_dir, *, sheet_name="Missing_Items", payload_builder=..., ...)` | `Dict` | Generic spreadsheet-to-payload/validation workflow. |
| `item_sync.create_inventory_items_from_sheet` | `(create_xlsx, output_dir, *, client=None, client_factory=None, payload_builder=..., ...)` | `Dict` | Generic validated spreadsheet creation workflow with injected client/auth policy. |
| `create_missing_inventory_items` | `(client, payloads, output_dir, results_filename=...)` | `(results, results_path)` | Creates missing items via `client.items.create(payload)` and writes a result CSV. |
| `load_fan_candidates` | `(path=Config.FAN_STOCK_FILE, accounts=None)` | `pandas.DataFrame` | Reads the FAN stock workbook `MAIN` sheet, filters live trade SKUs, and maps rows to Zoho item-master columns. |
| `compare_fan_items_with_inventory` | `(fan_file=Config.FAN_STOCK_FILE, output_dir=Config.FAN_OUTPUT_DIR, existing_items_file=None, client=None, accounts=None, max_pages=None, verbose=True)` | `Dict` | Thin FAN adapter over `compare_items_with_inventory`; supplies FAN parsing and account defaults. |
| `prepare_inventory_item_payloads` | `(create_xlsx=default missing-items XLSX, output_dir=Config.FAN_OUTPUT_DIR)` | `Dict` | Reads edited `Missing_Items`, writes create payload preview JSON/CSV and validation XLSX. |
| `create_inventory_items_from_sheet` | `(create_xlsx=default missing-items XLSX, output_dir=Config.FAN_OUTPUT_DIR, client=None, abort_on_blocking=True)` | `Dict` | Prepares payloads, aborts on blocking validation issues, and creates items through Zoho Inventory. |
| `build_create_payload` | `(row)` | `(payload, issues)` | FAN compatibility wrapper around `build_inventory_item_payload`. |
| `normalize_sku` | `(value)` | `str` | Uppercases and strips non-alphanumeric characters for matching. |

**Compare return dict shape**:
```python
{
    "candidates": DataFrame,
    "existing": DataFrame,
    "missing": DataFrame,
    "changed": DataFrame,
    "diff": Dict,
    "paths": {
        "missing_csv": Path,
        "missing_xlsx": Path,
        "existing_snapshot": Path,
        "changed_csv": Path,
        "changed_xlsx": Path,
    },
    "summary": {
        "fan_candidate_skus": int,
        "zoho_inventory_item_skus": int,
        "missing_fan_skus": int,
        "changed_fan_skus": int,
    },
}
```

---

## core/auth.py — Client Factories

| Function | Returns |
|---|---|
| `fetch_access_tokens(token_url=Config.TOKEN_URL)` | Runtime-only token map retrieved through SDK `HttpTokenProvider`; values are not persisted |
| `get_books_client(token=None, org_id=Config.ORG_ID, domain=Config.DOMAIN)` | `ZohoBooksAPI` instance |
| `get_workdrive_client(token=None, domain=Config.DOMAIN)` | `ZohoWorkdriveAPI` instance |
| `get_analytics_client(token=None, org_id=Config.PAYMENT_ANALYTICS_ORG_ID, domain=Config.DOMAIN)` | `ZohoAnalyticsAPI` instance |
| `get_inventory_client(token=None, org_id=Config.ORG_ID, domain=Config.DOMAIN, allow_books_token=False)` | `ZohoInventoryAPI` instance |

---

## core/customers.py — Customer Utilities

| Function | Signature | Returns | Description |
|---|---|---|---|
| `fetch_active_customers` | `(books_client)` | `List[Dict[str, Any]]` | Fetches all active customer contacts from Zoho Books, capturing standard fields and custom fields. |
| `find_same_day_payment_anomalies` | `(books_client, start_date=None, end_date=None, customer_id=None)` | `Dict[str, Any]` | Scans customer payments to find anomalies where a single customer has > 1 payment on the same day. |

**Return shape** for each item in the customer list:
```python
{
    "contact_id": str,
    "contact_number": str,
    "contact_name": str,
    "company_name": str,
    "status": str,
    "phone": str,
    "mobile": str,
    "email": str,
    "gst_no": str,
    "pan_no": str,
    "place_of_contact": str,
    "place_of_contact_formatted": str,
    "outstanding_receivable_amount": float,
    "unused_credits_receivable_amount": float,
    "cf_district": str,
    "cf_b_name": str,
    "cf_jurisdiction": str
}
```

---

## core/config.py — Config Class

All values loaded from `.env` at repo root. Defaults shown below.

| Config Key | Env Var | Default / Notes |
|---|---|---|
| `TOKEN_URL` | `TOKEN_URL` | `http://localhost:3000/server/new/tokens` |
| `ORG_ID` | `ORG_ID` | Zoho Books organisation ID |
| `DOMAIN` | `DOMAIN` | `"in"` (India) |
| `POLYCAB_FOLDER_ID` | `POLYCAB_FOLDER_ID` | WorkDrive folder for Polycab CNs |
| `FILES_DIR` | `FILES_DIR` | `input_files/polycab/cn` |
| `POLYCAB_LEDGER_PATH` | `POLYCAB_LEDGER_PATH` | Path to Polycab `.xls` ledger |
| `POLYCAB_VENDOR_ID` | `POLYCAB_VENDOR_ID` | Zoho Books contact ID for Polycab |
| `ZOHO_RSO_CN_ITEM_ID` | `ZOHO_RSO_CN_ITEM_ID` | Item ID for RSO credit notes |
| `ZOHO_SCHEME_CN_ITEM_ID` | `ZOHO_SCHEME_CN_ITEM_ID` | Item ID for Scheme credit notes |
| `ZOHO_GST0_TAX_ID` | `ZOHO_GST0_TAX_ID` | Tax ID for GST 0% / out-of-scope |
| `ZOHO_TAX_SETTINGS_ID` | `ZOHO_TAX_SETTINGS_ID` | Tax settings entity ID |
| `ZEISS_VENDOR_ID` | `ZEISS_VENDOR_ID` | Zoho Books contact ID for Zeiss |
| `ZEISS_LEDGER_PATH` | `ZEISS_LEDGER_PATH` | Path to Zeiss `.csv` ledger |
| `EXPECTED_LOCATION_ID` | `EXPECTED_LOCATION_ID` | Branch/location ID |
| `EXPECTED_LOCATION_NAME` | `EXPECTED_LOCATION_NAME` | `"Sri Bharath Electricals"` |
| `BANK_ACCOUNT_IDFC` | `BANK_ACCOUNT_IDFC` | IDFC bank account ID in Zoho Books |
| `BANK_ACCOUNT_HDFC` | `BANK_ACCOUNT_HDFC` | HDFC bank account ID in Zoho Books |
| `GSTIN_TO_VENDOR_ID` | `GSTIN_TO_VENDOR_ID` | JSON dict: GSTIN string → vendor ID |
| `FAN_STOCK_FILE` | `FAN_STOCK_FILE` | FAN stock workbook path |
| `FAN_OUTPUT_DIR` | `FAN_OUTPUT_DIR` | Output directory for FAN/Inventory sync files |
| `FAN_SALES_ACCOUNT_ID` | `FAN_SALES_ACCOUNT_ID` | Sales account ID for created inventory items |
| `FAN_PURCHASE_ACCOUNT_ID` | `FAN_PURCHASE_ACCOUNT_ID` | Purchase account ID for created inventory items |
| `FAN_INVENTORY_ACCOUNT_ID` | `FAN_INVENTORY_ACCOUNT_ID` | Inventory account ID for created inventory items |
| `ZOHO_GST18_TAX_ID` | `ZOHO_GST18_TAX_ID` | Intra-state GST 18% tax ID |
| `ZOHO_IGST18_TAX_ID` | `ZOHO_IGST18_TAX_ID` | Inter-state IGST 18% tax ID |


---

## core/exceptions.py & core/models.py — Exceptions and Models

### Custom Exceptions

All custom exceptions inherit from `ZohoUsableError` and a standard Python exception to preserve standard catchability in client code.

| Exception | Base Class | Description |
|---|---|---|
| `ZohoUsableError` | `Exception` | Base exception for all errors in this package. |
| `ZohoAuthError` | `ZohoUsableError`, `ValueError` | Raised when access token retrieval or Zoho client initialization fails. |
| `LedgerParsingError` | `ZohoUsableError`, `ValueError` | Raised when vendor ledger or GSTR-2B file parsing fails. |
| `LedgerNotImplementedError` | `LedgerParsingError`, `NotImplementedError` | Raised when a specific vendor key has no cleaner implementation. |
| `ReconciliationError` | `ZohoUsableError`, `ValueError` | Raised when reconciliation or matching calculations encounter configuration errors. |

### Dot-Accessible Dictionary (DotDict)

The `DotDict` class is a subclass of the native `dict` that enables dot-notation (attribute) access for nested dictionaries and matching collections, while remaining 100% compatible with standard dict key lookups.

All reconciliation and matching functions wrap their results in `DotDict` (e.g. `results.sales_invoice.matches[0][0].date`).

---

## Scripts (not importable — run directly)

| Script | Purpose | Key args / behaviour |
|---|---|---|
| `scripts/reconciliation/convert_zeiss_pdf.py` | Convert Carl Zeiss PDF ledgers to CSV and consolidate | Parses all `.pdf` statements in `input_files/zeiss/ledgers/` → `input_files/zeiss/Consolidated_Zeiss_Statements_2024_2025.csv` |
| `scripts/reconciliation/reconcile_vendor.py` | Reconcile Polycab vendor account (bills, payments, credits) vs ledger | Uses `Config.POLYCAB_VENDOR_ID`, `Config.POLYCAB_LEDGER_PATH` |
| `scripts/reconciliation/reconcile_zeiss.py` | Reconcile Zeiss vendor account vs ledger | Uses `Config.ZEISS_VENDOR_ID`, `Config.ZEISS_LEDGER_PATH` |
| `scripts/reconciliation/reconcile_bank.py` | Bank statement ↔ vendor ledger receipts | `reconcile_account(client, account_id, account_name, ledger_path, ...)` |
| `scripts/reconciliation/run_reconciliation.py` | Generic reconciliation entry point | Calls `reconcile_vendor_account` |
| `scripts/reconcile_gstr2b.py` | GSTR-2B vs Zoho Books reconciliation | Standalone, no library dependency |
| `scripts/export_fan_purchase_items.py` | Export and categorize all items in "Polycab Fan Purchase" account to CSV | Query Zoho Books API for items under the account, apply heuristics for type/tier/sweep/model/color, and save to `output/fan_purchase_items.csv` and `D:/workplace/fan_purchase_items.csv` |
| `scripts/propose_groups.py` | Propose group assignments for active items without group | Query Zoho Books API for current item groups, match active items without groups, and save to `output/proposed_group_assignments.csv` and `D:/workplace/proposed_group_assignments.csv` |
| `scripts/reconciliation/find_negative_stock.py` | Find items with negative stock in SBE | Audits and saves items with negative stock to `output/negative_stock_sbe.csv` and `D:/workplace/negative_stock_sbe.csv` (accepts `--location` override) |
| `scripts/inventory/fan_item_sync.py` | FAN stock workbook ↔ Zoho Inventory item sync | Writes missing-item CSV/XLSX by default; supports `--prepare-create-items` and `--execute-create-items` |
| `scripts/inventory/update_adjustment_accounts.py` | Audit and update inventory adjustment accounts | Excludes zero-effect adjustments, audits non-zero adjustments, maps warehouses to correct target account IDs, and executes updates. Supports `--from-csv` to process target lists directly from the output CSV. |
| `scripts/inventory/group_fan_items.py` | Export and cluster Zoho fan items into variant groups | Fetches existing standalone fan items, exports them to CSV, and generates proposed Item Groups/attribute mappings CSV. |
| `scripts/inventory/execute_grouping.py` | Group manually edited fan items in Zoho | Reads a category CSV file, updates item names, and POSTs groupings to Zoho items/grouping API workaround. |
| `scripts/find_items_with_unit_nos.py` | Scan Zoho Books items for non-standard unit cases | Fetches items incrementally with pagination and caches them to `output/zoho_items.json` |
| `scripts/update_sku_units.py` | Update items unit to "NOS" for a target list of SKUs | Supports `--execute` for applying updates and defaults to dry-run mode |
| `scripts/books/fetch_active_customers.py` | Export active customers to CSV | Fetches all active customer contacts from Zoho Books and saves key columns to a CSV file. |
| `scripts/books/update_customer_mobiles.py` | Update incorrect customer mobiles in bulk | Norms mobile numbers in incorrect_phone_customers.csv and PUTs updates. Supports `--execute`. |
| `scripts/books/find_payment_anomalies.py` | Find same-day customer payment anomalies | Finds and reports accounts/days with multiple payment entries. Supports `--start-date`, `--end-date`, `--customer-id`, `--output`. |
| `scripts/inventory/clone_zeiss_items.py` | Clone items and rename original SKUs | Fetches original items from CSV, renames original SKUs to `_old` and clones items with Zeiss accounts. Supports `--execute`. |
| `scripts/books/update_bill_items.py` | Update bill line item IDs | Updates target bill line items to map old item IDs to newly cloned Zeiss item IDs. Supports `--execute`. |
| `scripts/inventory/delete_old_items.py` | Cleanup old SKU items | Attempts to delete original items renamed to `_old`. If deletion fails due to transaction history, marks them inactive in bulk. Supports `--execute`. |
| `scripts/books/find_item_transactions.py` | Find item transactions and update CSV | Overwrites the input CSV to contain only the 17 items that failed deletion, and prints/saves details of all transactions containing them. |

---

## Supported Vendors

| Vendor | `vendor_key` | File Type | Detection Rule |
|---|---|---|---|
| Polycab India Ltd | `"polycab"` | `.xls` (Excel) | Filename starts with `277498` or contains `polycab` |
| Carl Zeiss India | `"zeiss"` | `.csv` | Filename contains `zeiss` |

---

## Dependencies

| Package | Purpose |
|---|---|
| `zoho_sdk` | Zoho Books + WorkDrive API client (install separately: `pip install -e ../zoho_sdk`) |
| `xlrd` | Read Polycab `.xls` ledger files |
| `pdfplumber` | Extract text from Polycab PDF credit notes |
| `openpyxl` | Excel file support |
| `pandas` | Tabular Excel/CSV transforms for reconciliation and Inventory workflows |
| `python-dotenv` | Load `.env` config |
| `requests` | HTTP calls |

---

## Common Patterns

**Typical reconciliation script flow:**
```python
from zoho_usable_functions import get_books_client, fetch_access_tokens
from zoho_usable_functions import reconcile_vendor_account

tokens = fetch_access_tokens()
client = get_books_client(token=tokens["access_token"])
result = reconcile_vendor_account(client, vendor_id="...", vendor_ledger_path="input_files/polycab/ledger/...")
```

**Typical credit memo flow:**
```python
from zoho_usable_functions import get_books_client, get_workdrive_client
from zoho_usable_functions import create_vendor_credit_from_pdf, upload_vendor_credit_attachment, upload_to_workdrive

tokens = fetch_access_tokens()
books = get_books_client(token=tokens["access_token"])
wd    = get_workdrive_client(token=tokens["workdrive_access_token"])

vc    = create_vendor_credit_from_pdf(books, "input_files/polycab/cn/CM-12345.pdf")
upload_vendor_credit_attachment(books, vc["vendor_credit_id"], "input_files/polycab/cn/CM-12345.pdf")
upload_to_workdrive(wd, Config.POLYCAB_FOLDER_ID, "input_files/polycab/cn/CM-12345.pdf")
```

---

## Workflows

### 1. Process Polycab Credit Memos (batch — most common task)

Drop all `CM-*.pdf` or `CN-*.pdf` files into `input_files/polycab/cn/`, then run the script.
The script is **idempotent** — it checks existing Zoho Books vendor credits and WorkDrive files before acting,
so re-running is always safe.

**Steps performed automatically by the script:**
1. Fetch existing vendor credits from Zoho Books → build a skip-set to avoid duplicates
2. Fetch existing files in the WorkDrive folder → build a skip-set to avoid re-uploads
3. For each PDF in `input_files/polycab/cn/` (files named `CM-*` or `CN-*`):
   - Parse PDF → extract CN number, date, amount, description
   - Classify as RSO CN or Scheme CN (based on presence of `RSO Number :` in PDF text)
   - If CN number not already in Zoho Books → POST vendor credit
   - Attach the PDF to the vendor credit in Zoho Books
   - If filename not already in WorkDrive → upload PDF to WorkDrive folder

**Run:**
```bash
uv run python scripts/credit_memos/process_credit_memo.py
```

**Optional overrides:**
```bash
uv run python scripts/credit_memos/process_credit_memo.py \
  --files-dir input_files/polycab/cn \
  --folder-id <workdrive_folder_id> \
  --vendor-id <zoho_vendor_id>
```

---

### 2. Reconcile Polycab Vendor Account (bills, payments, credits vs ledger)

Place the Polycab Excel ledger (`.xls`) in `input_files/polycab/ledger/` and set `POLYCAB_LEDGER_PATH` in `.env`.

**Steps performed automatically:**
1. Read ledger file → detect date range from header rows
2. Fetch from Zoho Books for that date range: Bills, Vendor Payments, Vendor Credits
3. Reconcile each document type using 3-pass matching (exact → strong → weak)
4. Print match/unmatched summary table to stdout

**Run (uses defaults from `.env`):**
```bash
uv run python scripts/reconciliation/reconcile_vendor.py
```

**Optional overrides:**
```bash
uv run python scripts/reconciliation/reconcile_vendor.py \
  --vendor-id <id> \
  --ledger-path input_files/polycab/ledger/277498_ReconciliationLedger_....xls \
  --date-tolerance 20 \
  --amount-tolerance 0.05
```

**Output:** Printed table per document type — matched count, unmatched-in-Books, unmatched-in-Ledger.

---

### 3. Reconcile Zeiss Vendor Account (CSV statement vs Zoho Books)

Place the Zeiss CSV in `input_files/zeiss/` and set `ZEISS_LEDGER_PATH` in `.env`.

**Run (uses defaults from `.env`):**
```bash
uv run python scripts/reconciliation/reconcile_zeiss.py
```

**Optional overrides:**
```bash
uv run python scripts/reconciliation/reconcile_zeiss.py \
  --vendor-id <id> \
  --ledger-path input_files/zeiss/ZeissOct2025_Statement.csv \
  --date-tolerance 7 \
  --amount-tolerance 0.05
```

**Output:** Per-document-type table + grand summary with overall match rate %.

---

### 4. Reconcile Bank Accounts vs Polycab Ledger

Matches bank withdrawals (IDFC-SBE + HDFC-SBE) against receipt rows in the Polycab ledger file.
Always reconciles **both** `BANK_ACCOUNT_IDFC` and `BANK_ACCOUNT_HDFC` in one run.

**Run:**
```bash
uv run python scripts/reconciliation/reconcile_bank.py
```

**Optional overrides:**
```bash
uv run python scripts/reconciliation/reconcile_bank.py \
  --ledger-path input_files/polycab/ledger/277498_....xls \
  --date-tolerance 10 \
  --amount-tolerance 0.0
```

---

### 5. Scan All Bank Accounts vs Polycab Ledger (discovery)

Use when you don't know which bank account has matches — scans all `bank`/`payment_clearing` accounts.

**Run:**
```bash
uv run python scripts/reconciliation/run_reconciliation.py \
  --ledger-path input_files/polycab/ledger/277498_....xls
```

---

### 6. One-off: Parse a single Polycab PDF (inspect/debug)

```python
from zoho_usable_functions import parse_polycab_credit_memo
details = parse_polycab_credit_memo("input_files/polycab/cn/CM-12345.pdf")
print(details)
# {"vendor_credit_number": "...", "date": "...", "amount": ..., "description": "...", "raw_text": "..."}
```

---

### 7. One-off: Parse a ledger file (inspect/debug)

```python
from zoho_usable_functions import clean_ledger_file, get_ledger_metadata
meta    = get_ledger_metadata("input_files/polycab/ledger/277498_....xls")
entries = clean_ledger_file("input_files/polycab/ledger/277498_....xls")
print(meta)       # {"start_date": "...", "end_date": "...", "party_name": "...", "opening_balance": ...}
print(entries[0]) # First transaction dict
```

---

## Execution Reference

### How to Run Scripts

All scripts must be run from the **project root** using `uv run`:

```bash
uv run python scripts/<subdir>/<script_name>.py [--arg value ...]
```

**Why `uv run`?** It automatically activates `.venv`. Alternative: `.venv/bin/python scripts/...`

### Quick Command Reference

| Task | Command |
|---|---|
| Process all Polycab credit memo PDFs | `uv run python scripts/credit_memos/process_credit_memo.py` |
| Convert Zeiss PDF ledgers to CSV | `uv run python scripts/reconciliation/convert_zeiss_pdf.py` |
| Reconcile Polycab vendor (bills/payments/credits) | `uv run python scripts/reconciliation/reconcile_vendor.py` |
| Reconcile Zeiss vendor | `uv run python scripts/reconciliation/reconcile_zeiss.py` |
| Reconcile bank accounts vs Polycab ledger | `uv run python scripts/reconciliation/reconcile_bank.py` |
| Scan all bank accounts (discovery) | `uv run python scripts/reconciliation/run_reconciliation.py` |
| Export & categorize fan purchase items to CSV | `uv run python scripts/export_fan_purchase_items.py` |
| Propose group assignments for items without group | `uv run python scripts/propose_groups.py` |
| Find items with negative stock in location SBE | `uv run python scripts/reconciliation/find_negative_stock.py` |
| Scan Zoho Books items for 'Nos' unit | `uv run python scripts/find_items_with_unit_nos.py` |
| Update target items unit to 'NOS' | `uv run python scripts/update_sku_units.py --execute` |
| Audit/update adjustment accounts | `uv run python scripts/inventory/update_adjustment_accounts.py [--execute] [--from-csv]` |
| Export and group fan items | `uv run python scripts/inventory/group_fan_items.py` |
| Execute item groupings in Zoho | `uv run python scripts/inventory/execute_grouping.py [--execute] [--csv FILE]` |
| Fetch active customers to CSV | `uv run python scripts/books/fetch_active_customers.py` |
| Update customer mobiles in bulk | `uv run python scripts/books/update_customer_mobiles.py [--execute]` |
| Find same-day customer payment anomalies | `uv run python scripts/books/find_payment_anomalies.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--customer-id ID]` |
| Clone items and rename original SKUs | `uv run python scripts/inventory/clone_zeiss_items.py [--execute]` |
| Update target bill line items to cloned item IDs | `uv run python scripts/books/update_bill_items.py [--execute] [--bill-id ID]` |
| Attempt to delete or inactivate old SKU items | `uv run python scripts/inventory/delete_old_items.py [--execute]` |
| Find item transactions and update CSV | `uv run python scripts/books/find_item_transactions.py` |

### What INDEX.md Covers for Execution

✅ Which script to run for each task  
✅ All `--arg` flags with their defaults  
✅ Which defaults are sourced from `.env`  
✅ Where to place input files before running  
✅ What output / summary to expect  
❌ Actual `.env` values — agent must read `.env` file if overrides are needed  
❌ Error diagnosis beyond what the script prints — open the source file only then  
