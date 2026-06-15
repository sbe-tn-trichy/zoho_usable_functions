"""
reconciliation._utils
~~~~~~~~~~~~~~~~~~~~~
Low-level, pure helper functions shared across all reconciliation modules.
No Zoho API calls, no file I/O — safe to import anywhere.
"""
import logging
from datetime import datetime, date
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def parse_date(date_str: Any) -> Optional[date]:
    """Safely parse various date formats into a datetime.date object."""
    if not date_str:
        return None
    if isinstance(date_str, (date, datetime)):
        return date_str if isinstance(date_str, date) else date_str.date()
    try:
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(str(date_str).strip().split("T")[0]).date()
        except ValueError:
            return None


def get_abs_amount(tx: Dict[str, Any]) -> float:
    """Extract absolute amount from a bank transaction dict."""
    try:
        return abs(float(tx.get("amount", 0.0)))
    except (ValueError, TypeError):
        return 0.0


def ref_match(ref1: Any, ref2: Any) -> bool:
    """Compare two reference numbers case-insensitively and stripped of whitespace."""
    r1 = str(ref1 or "").strip().lower()
    r2 = str(ref2 or "").strip().lower()
    return bool(r1 and r2 and r1 == r2)
