# Zoho Usable Functions

High-level helper functions and automated workflows built on top of the Zoho SDK.

## Project maturity boundary

Confirmed reconciliation and credit-memo modules are owned by the unified
`zoho-sdk` distribution under its top-level `workflows` package.

This repository remains the incubation area for trial workflows, currently:

- FAN and generic inventory item synchronization
- Zoho Creator/Analytics payment reconciliation
- Customer unused-credit and payment-anomaly utilities

Legacy `zoho_usable_functions.reconciliation` and
`zoho_usable_functions.credit_memos` import paths remain as lightweight module
aliases; they contain no copied workflow implementations. New code should
import promoted behavior from `workflows` directly. Experimental work remains
here until it is ready to move into the SDK.

## Installation

Install in editable mode along with `zoho_sdk`:
```bash
pip install -e "../zoho_sdk[workflows]"
pip install -e .
```

## Credentials

Copy `.env.example` to `.env` and populate local organization configuration.
The `.env` file is ignored by Git. Access tokens are retrieved from `TOKEN_URL`
at runtime and are not persisted by this package or `zoho_sdk`. Never add token
values to `.env.example`, source code, logs, or generated reports.

## Architecture

`zoho_sdk` owns generic Zoho clients plus confirmed reconciliation and Polycab
credit-memo workflows. This package owns incubating and company-specific
utilities such as inventory synchronization, GST reconciliation, payment
reconciliation, and customer audits.
