"""Compatibility alias for the SDK-owned Zeiss PDF workflow."""

import sys

from workflows.vendor_ledger_reconciliation import zeiss_pdf as _sdk_module

sys.modules[__name__] = _sdk_module
