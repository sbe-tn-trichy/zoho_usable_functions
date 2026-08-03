"""Compatibility alias for the SDK-owned Polycab credit-memo workflow."""

import sys

from workflows.polycab_credit_memos import processor as _sdk_module

sys.modules[__name__] = _sdk_module
