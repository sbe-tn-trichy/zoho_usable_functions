"""Compatibility alias for SDK-owned reconciliation matching primitives."""

import sys

from workflows.core import matching as _sdk_module

sys.modules[__name__] = _sdk_module
