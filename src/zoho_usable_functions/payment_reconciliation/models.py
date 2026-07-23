from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CreatorPayment:
    id: str
    date: Optional[date]
    amount: float
    customer_id: str
    reference: str = ""
    customer_name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BankStatementLine:
    id: str
    date: Optional[date]
    amount: float
    description: str = ""
    reference: str = ""
    bank_account_id: str = ""
    bank_name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyticsCustomer:
    customer_id: str
    bank_transaction_id: str = ""
    reference: str = ""
    search_key: str = ""
    customer_name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentMatch:
    creator_payment: CreatorPayment
    bank_statement_line: BankStatementLine
    analytics_customer: AnalyticsCustomer
    confidence: str = "100%"
    reason: str = "amount, date, customer, and reference/search key matched uniquely"
