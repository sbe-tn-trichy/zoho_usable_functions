"""Compatibility alias for the SDK-owned vendor-ledger cleaner."""

import sys

from workflows.vendor_ledger_reconciliation import cleaner as _sdk_module

sys.modules[__name__] = _sdk_module
