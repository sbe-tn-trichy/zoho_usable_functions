# Antigravity Python Backend Architecture Blueprints

This document contains production-ready, zero-compromise prompt frameworks optimized for Python backend engineering within Google's Antigravity autonomous AI workspace.

---

## 1. System Design & Implementation Blueprint
Use this prompt framework when you want Antigravity to architect and write a backend feature or service from scratch.

### The System Architecture Prompt
```text
Act as an expert software architect specializing in scalable Python backend design. I want you to design the system architecture and generate a complete implementation plan for the following project:

usable functions for zoho services

You must adhere strictly to the following engineering mandates:
1. High Modularity: Separate concerns cleanly using appropriate architectural patterns (e.g., Service-Repository pattern, Clean Architecture, or Domain-Driven Design).
2. Zero Code Repetition (DRY): Absolutely no duplicate code logic. Extract reusable workflows into utility modules, base classes, or middleware.
3. Leverage Frameworks: Do not reinvent the wheel. Utilize industry-standard Python libraries and frameworks (e.g., FastAPI/Litestar for APIs, Pydantic v2 for data validation, SQLAlchemy/SQLModel for ORM, Celery/Drama for async tasks, pytest for testing) instead of writing custom boilerplate.
4. Production-Ready Testing: Every component must feature a comprehensive, modular suite of unit tests using pytest, utilizing fixtures to prevent setup duplication.
5. No Shortcuts: Do not use placeholder code, `pass` statements, or "// TODO" comments. Write the complete, functional implementation.

Execute this implementation sequentially across these strict phases:

PHASE 1: System Design & Edge-Case Investigation
- Define the directory tree layout explicitly.
- Map data flows, database schemas, and external dependencies.
- Investigate, document, and explicitly rule out edge cases (e.g., race conditions, payload limits, network dropouts, database connection pool exhaustion). Resolve these in the design phase before generating code.

PHASE 2: Modular Implementation Plan
- Generate clean, optimized, fully-typed (PEP 484) Python code file-by-file across the project workspace.
- Ensure strict separation of configuration, routing, business logic, and data access layers.

PHASE 3: Automated Verification
- Autonomously generate complete pytest suites covering standard, edge-case, and error-handling paths.
- Run the test suite within the workspace, catch any runtime or logical errors, and self-correct the codebase dynamically until all verification passes.
```

# Directory Index: zoho_usable_functions
- **Absolute Path:** `/Users/vak/Documents/workspace/zoho_usable_functions`
- **Relative Path:** `./`

> [!IMPORTANT]
> **MANDATORY FIRST STEP**: Before doing any work in this repository, read [INDEX.md](file:///Users/vak/Documents/workspace/zoho_usable_functions/INDEX.md) in the project root. It contains the full module map, API client signatures, parameters, and return types. Do not open source files to figure out what functions exist or what they return.

## Repo Conventions

- All library code lives in `src/zoho_usable_functions/`
- Runner scripts live in `scripts/` and are NOT part of the importable library
- Input files (ledgers, PDFs) live in `files/` (gitignored)
- Config is always loaded via `Config` class in `core/config.py` — never hardcode IDs
- The Zoho SDK (`zoho_sdk`) is a sibling package installed separately

## When Adding New Functions

1. Implement in the appropriate module (`reconciliation/`, `credit_memos/`, or `core/`)
2. Export from `src/zoho_usable_functions/__init__.py`
3. **Update `INDEX.md`** — add the function to the relevant table and document return shape

## MANDATORY: Keep INDEX.md in Sync

**INDEX.md is the source of truth for this repo. It MUST be updated whenever any of the following change:**

- A function is added, removed, or renamed
- A function's signature, parameters, or return shape changes
- A new module or file is added or deleted
- A new `Config` key or `.env` variable is introduced
- A new vendor is supported (new `vendor_key` value)

**This is not optional.** If you modify code and do NOT update `INDEX.md`, you are leaving stale information that will mislead future agents and waste tokens.

**Rule**: Every task that touches source code must end with a check — "Does INDEX.md still accurately reflect what I changed?" If not, update it before finishing.

## Functions Index (Public API Clients & Helpers)
*For complete method signatures and details, refer to [INDEX.md](file:///Users/vak/Documents/workspace/zoho_usable_functions/INDEX.md).*

| Class / Symbol | Type | Service / Domain | Description |
| --- | --- | --- | --- |
| `get_ledger_metadata` | Function | Reconciliation | Extracts date range + party info from a ledger file (Polycab/Zeiss) |
| `clean_ledger_file` | Function | Reconciliation | Parses and normalizes a vendor ledger |
| `match_ledger_entries` | Function | Reconciliation | Bank withdrawals ↔ Zoho vendor payments matching |
| `match_bank_with_vendor_ledger` | Function | Reconciliation | Bank withdrawals (Zoho Books) ↔ vendor ledger receipts (local file) |
| `reconcile_vendor_account` | Function | Reconciliation | Full 4-way reconciliation (bills, payments, credits, debits vs ledger) |
| `reconcile_vendor` | Function | Reconciliation | High-level wrapper that auto-initializes the Books client and auto-detects vendor from ledger path if omitted. |
| `parse_polycab_credit_memo` | Function | Credit Memos | Extracts CN details from Polycab PDF |
| `create_vendor_credit_from_pdf` | Function | Credit Memos | Parses PDF + POSTs vendor credit to Zoho Books |
| `upload_vendor_credit_attachment` | Function | Credit Memos | Attaches PDF file to a Vendor Credit in Zoho Books |
| `upload_to_workdrive` | Function | Credit Memos | Uploads PDF to Zoho WorkDrive folder |
| `fetch_access_tokens` | Function | Core/Auth | Fetches/refreshes Zoho Access Tokens |
| `get_books_client` | Function | Core/Auth | Factory for ZohoBooksAPI client instance |
| `get_workdrive_client` | Function | Core/Auth | Factory for ZohoWorkdriveAPI client instance |

## Subdirectories
- `files`
- `logs`
- `output`
- `scripts`
- `src`
- `tests`

## File Inventory
| File Name | Extension | Description |
| --- | --- | --- |
| .gitignore | (none) | Git exclusion patterns (ignores `.venv`, `files/`, etc.) |
| GEMINI.md | .md | Agent instruction file with backend architecture blueprints |
| INDEX.md | .md | Code index mapping all modules and public helper methods |
| pyproject.toml | .toml | Package metadata and dependencies config |
| README.md | .md | Basic package installation instructions |
| .env | .env | Environment variables config for development / credentials |
