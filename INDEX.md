# zoho_usable_functions — Code Index

> **AI AGENT INSTRUCTION**: Read this file first before opening any source file.
> It maps the entire codebase. Only open source files when you need implementation details beyond what is here.

---

## Project Purpose

High-level Python helper library + scripts built on top of `zoho_sdk`.
Two main domains:
1. **Reconciliation** — Match Zoho Books records against external vendor/bank ledger files
2. **Credit Memos** — Parse Polycab PDF credit notes and post them to Zoho Books

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
│   │   └── matcher.py               # Re-export facade (public API unchanged)
│   └── credit_memos/
│       └── processor.py             # Parse Polycab PDFs + post to Zoho Books
├── scripts/                         # Standalone runner scripts (not importable library)
│   ├── reconciliation/
│   │   ├── convert_zeiss_pdf.py     # Convert Zeiss PDF statements → CSV and consolidate
│   │   ├── reconcile_bank.py        # Bank account ↔ vendor ledger reconciliation
│   │   ├── reconcile_vendor.py      # Vendor account full reconciliation (Polycab)
│   │   ├── reconcile_zeiss.py       # Vendor account full reconciliation (Zeiss)
│   │   └── run_reconciliation.py    # Generic reconciliation entry point
│   ├── reconcile_gstr2b.py          # GSTR-2B reconciliation (standalone)
│   └── credit_memos/                # Credit memo processing scripts
├── files/                           # Input data files (ledgers, PDFs) — gitignored
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

### credit_memos.processor

| Function | Signature | Returns | Notes |
|---|---|---|---|
| `parse_polycab_credit_memo` | `(pdf_path: str)` | `Dict` | Extracts CN number, date, amount, description from Polycab PDF. Uses `pdfplumber`. |
| `create_vendor_credit_from_pdf` | `(books_client, pdf_path, vendor_name="Polycab", account_name="Polycab Scheme - Expense")` | `Dict` | Parses PDF → classifies RSO/Scheme → POSTs vendor credit to Zoho Books. |
| `upload_vendor_credit_attachment` | `(books_client, vendor_credit_id: str, pdf_path: str)` | `Dict` | Attaches PDF file to a Vendor Credit in Zoho Books. |
| `upload_to_workdrive` | `(wd_client, folder_id: str, pdf_path: str)` | `Dict` | Uploads PDF to Zoho WorkDrive folder. |

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

## core/auth.py — Client Factories

| Function | Returns |
|---|---|
| `fetch_access_tokens(token_url=Config.TOKEN_URL)` | `{"access_token": ..., "workdrive_access_token": ...}` |
| `get_books_client(token=None, org_id=Config.ORG_ID, domain=Config.DOMAIN)` | `ZohoBooksAPI` instance |
| `get_workdrive_client(token=None, domain=Config.DOMAIN)` | `ZohoWorkdriveAPI` instance |

---

## core/config.py — Config Class

All values loaded from `.env` at repo root. Defaults shown below.

| Config Key | Env Var | Default / Notes |
|---|---|---|
| `TOKEN_URL` | `TOKEN_URL` | `http://localhost:3000/server/new/tokens` |
| `ORG_ID` | `ORG_ID` | Zoho Books organisation ID |
| `DOMAIN` | `DOMAIN` | `"in"` (India) |
| `POLYCAB_FOLDER_ID` | `POLYCAB_FOLDER_ID` | WorkDrive folder for Polycab CNs |
| `FILES_DIR` | `FILES_DIR` | `files/polycab/cn` |
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

---

## Scripts (not importable — run directly)

| Script | Purpose | Key args / behaviour |
|---|---|---|
| `scripts/reconciliation/convert_zeiss_pdf.py` | Convert Carl Zeiss PDF ledgers to CSV and consolidate | Parses all `.pdf` statements in `files/zeiss/ledgers/` → `files/zeiss/Consolidated_Zeiss_Statements_2024_2025.csv` |
| `scripts/reconciliation/reconcile_vendor.py` | Reconcile Polycab vendor account (bills, payments, credits) vs ledger | Uses `Config.POLYCAB_VENDOR_ID`, `Config.POLYCAB_LEDGER_PATH` |
| `scripts/reconciliation/reconcile_zeiss.py` | Reconcile Zeiss vendor account vs ledger | Uses `Config.ZEISS_VENDOR_ID`, `Config.ZEISS_LEDGER_PATH` |
| `scripts/reconciliation/reconcile_bank.py` | Bank statement ↔ vendor ledger receipts | `reconcile_account(client, account_id, account_name, ledger_path, ...)` |
| `scripts/reconciliation/run_reconciliation.py` | Generic reconciliation entry point | Calls `reconcile_vendor_account` |
| `scripts/reconcile_gstr2b.py` | GSTR-2B vs Zoho Books reconciliation | Standalone, no library dependency |

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
result = reconcile_vendor_account(client, vendor_id="...", vendor_ledger_path="files/polycab/ledger/...")
```

**Typical credit memo flow:**
```python
from zoho_usable_functions import get_books_client, get_workdrive_client
from zoho_usable_functions import create_vendor_credit_from_pdf, upload_vendor_credit_attachment, upload_to_workdrive

tokens = fetch_access_tokens()
books = get_books_client(token=tokens["access_token"])
wd    = get_workdrive_client(token=tokens["workdrive_access_token"])

vc    = create_vendor_credit_from_pdf(books, "files/polycab/cn/CM-12345.pdf")
upload_vendor_credit_attachment(books, vc["vendor_credit_id"], "files/polycab/cn/CM-12345.pdf")
upload_to_workdrive(wd, Config.POLYCAB_FOLDER_ID, "files/polycab/cn/CM-12345.pdf")
```

---

## Workflows

### 1. Process Polycab Credit Memos (batch — most common task)

Drop all `CM-*.pdf` or `CN-*.pdf` files into `files/polycab/cn/`, then run the script.
The script is **idempotent** — it checks existing Zoho Books vendor credits and WorkDrive files before acting,
so re-running is always safe.

**Steps performed automatically by the script:**
1. Fetch existing vendor credits from Zoho Books → build a skip-set to avoid duplicates
2. Fetch existing files in the WorkDrive folder → build a skip-set to avoid re-uploads
3. For each PDF in `files/polycab/cn/` (files named `CM-*` or `CN-*`):
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
  --files-dir files/polycab/cn \
  --folder-id <workdrive_folder_id> \
  --vendor-id <zoho_vendor_id>
```

---

### 2. Reconcile Polycab Vendor Account (bills, payments, credits vs ledger)

Place the Polycab Excel ledger (`.xls`) in `files/polycab/ledger/` and set `POLYCAB_LEDGER_PATH` in `.env`.

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
  --ledger-path files/polycab/ledger/277498_ReconciliationLedger_....xls \
  --date-tolerance 20 \
  --amount-tolerance 0.05
```

**Output:** Printed table per document type — matched count, unmatched-in-Books, unmatched-in-Ledger.

---

### 3. Reconcile Zeiss Vendor Account (CSV statement vs Zoho Books)

Place the Zeiss CSV in `files/zeiss/` and set `ZEISS_LEDGER_PATH` in `.env`.

**Run (uses defaults from `.env`):**
```bash
uv run python scripts/reconciliation/reconcile_zeiss.py
```

**Optional overrides:**
```bash
uv run python scripts/reconciliation/reconcile_zeiss.py \
  --vendor-id <id> \
  --ledger-path files/zeiss/ZeissOct2025_Statement.csv \
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
  --ledger-path files/polycab/ledger/277498_....xls \
  --date-tolerance 10 \
  --amount-tolerance 0.0
```

---

### 5. Scan All Bank Accounts vs Polycab Ledger (discovery)

Use when you don't know which bank account has matches — scans all `bank`/`payment_clearing` accounts.

**Run:**
```bash
uv run python scripts/reconciliation/run_reconciliation.py \
  --ledger-path files/polycab/ledger/277498_....xls
```

---

### 6. One-off: Parse a single Polycab PDF (inspect/debug)

```python
from zoho_usable_functions import parse_polycab_credit_memo
details = parse_polycab_credit_memo("files/polycab/cn/CM-12345.pdf")
print(details)
# {"vendor_credit_number": "...", "date": "...", "amount": ..., "description": "...", "raw_text": "..."}
```

---

### 7. One-off: Parse a ledger file (inspect/debug)

```python
from zoho_usable_functions import clean_ledger_file, get_ledger_metadata
meta    = get_ledger_metadata("files/polycab/ledger/277498_....xls")
entries = clean_ledger_file("files/polycab/ledger/277498_....xls")
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

### What INDEX.md Covers for Execution

✅ Which script to run for each task  
✅ All `--arg` flags with their defaults  
✅ Which defaults are sourced from `.env`  
✅ Where to place input files before running  
✅ What output / summary to expect  
❌ Actual `.env` values — agent must read `.env` file if overrides are needed  
❌ Error diagnosis beyond what the script prints — open the source file only then  
