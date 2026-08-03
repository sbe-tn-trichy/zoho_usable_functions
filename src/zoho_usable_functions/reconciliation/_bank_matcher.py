"""Compatibility alias for the SDK-owned bank reconciliation engine."""

import sys

from workflows.bank_reconciliation import _matcher as _sdk_module

sys.modules[__name__] = _sdk_module
