"""Compatibility alias for the SDK-owned vendor reconciliation engine."""

import sys

from workflows.vendor_ledger_reconciliation import _reconciler as _sdk_module

sys.modules[__name__] = _sdk_module
