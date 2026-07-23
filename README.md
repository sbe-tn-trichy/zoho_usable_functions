# Zoho Usable Functions

High-level helper functions and automated workflows built on top of the Zoho SDK.

## Project maturity boundary

Confirmed reconciliation and credit-memo modules have been promoted into the
sibling project `../zoho_sdk_advanced`.

This repository remains the incubation area for trial workflows, currently:

- FAN and generic inventory item synchronization
- Zoho Creator/Analytics payment reconciliation
- Customer unused-credit and payment-anomaly utilities

The confirmed modules are temporarily retained here as compatibility copies
while callers migrate to `zoho_sdk_advanced`. New production work should import
the promoted package; experimental work should stay here until it satisfies the
promotion checklist in `../zoho_sdk_advanced/INDEX.md`.

## Installation

Install in editable mode along with `zoho_sdk`:
```bash
pip install -e ../zoho_sdk
pip install -e .
```

## Credentials

Copy `.env.example` to `.env` and populate local organization configuration.
The `.env` file is ignored by Git. Access tokens are retrieved from `TOKEN_URL`
at runtime and are not persisted by this package or `zoho_sdk`. Never add token
values to `.env.example`, source code, logs, or generated reports.

## Architecture

`zoho_sdk` owns generic Zoho authentication, HTTP clients, resources,
pagination, and actions. This package owns company workflows such as vendor
reconciliation, credit-memo processing, and FAN inventory synchronization.
