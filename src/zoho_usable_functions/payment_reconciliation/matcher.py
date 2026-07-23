import csv
import logging
import re
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from zoho import ZohoAnalyticsAPI

from zoho_usable_functions.core.config import Config
from zoho_usable_functions.reconciliation._utils import get_abs_amount, parse_date

from .models import AnalyticsCustomer, BankStatementLine, CreatorPayment, PaymentMatch

logger = logging.getLogger(__name__)


def _first(record: Dict[str, Any], names: Sequence[str], default: Any = "") -> Any:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    lower_map = {str(k).lower(): v for k, v in record.items()}
    for name in names:
        value = lower_map.get(name.lower())
        if value not in (None, ""):
            return value
    return default


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if cleaned in ("", "-", ".", "-."):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _norm_amount(value: float) -> int:
    return int(round(float(value) * 100))


def _contains_or_equals(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _compact_json(value: Any) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PaymentReconciliationConfig:
    creator_app_link_name: str = getattr(Config, "PAYMENT_CREATOR_APP_LINK_NAME", "")
    creator_report_link_name: str = getattr(Config, "PAYMENT_CREATOR_REPORT_LINK_NAME", "")
    analytics_workspace_id: str = getattr(Config, "PAYMENT_ANALYTICS_WORKSPACE_ID", "")
    analytics_view_id: str = getattr(Config, "PAYMENT_ANALYTICS_VIEW_ID", "")
    bank_account_ids: Tuple[str, ...] = field(
        default_factory=lambda: tuple(
            account_id
            for account_id in (
                getattr(Config, "BANK_ACCOUNT_IDFC", ""),
                getattr(Config, "BANK_ACCOUNT_HDFC", ""),
                getattr(Config, "BANK_ACCOUNT_HDFC_AGENCIES", ""),
                getattr(Config, "BANK_ACCOUNT_ICICI", ""),
            )
            if account_id
        )
    )
    bank_account_names: Dict[str, str] = field(
        default_factory=lambda: {
            account_id: account_name
            for account_id, account_name in (
                (getattr(Config, "BANK_ACCOUNT_IDFC", ""), "IDFC"),
                (getattr(Config, "BANK_ACCOUNT_HDFC", ""), "HDFC"),
                (getattr(Config, "BANK_ACCOUNT_HDFC_AGENCIES", ""), "HDFC Agencies"),
                (getattr(Config, "BANK_ACCOUNT_ICICI", ""), "ICICI"),
            )
            if account_id
        }
    )
    date_tolerance_days: int = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    creator_criteria: Optional[str] = None
    confirm_dry_run: bool = True


@dataclass(frozen=True)
class PaymentReconciliationResult:
    exact_matches: List[PaymentMatch]
    confirmed_matches: List[PaymentMatch]
    confirmation_responses: List[Dict[str, Any]]
    ambiguous_matches: List[Dict[str, Any]]
    unmatched_creator_payments: List[CreatorPayment]
    unmatched_bank_statement_lines: List[BankStatementLine]


CSV_FIELDS = [
    "status",
    "confidence",
    "reason",
    "creator_payment_id",
    "creator_date",
    "creator_amount",
    "creator_customer_id",
    "creator_customer_name",
    "creator_reference",
    "bank_transaction_id",
    "bank_account_id",
    "bank_name",
    "bank_date",
    "bank_amount",
    "bank_reference",
    "bank_description",
    "analytics_customer_id",
    "analytics_customer_name",
    "analytics_bank_transaction_id",
    "analytics_reference",
    "analytics_search_key",
]


UNMATCHED_BANK_EXPORT_FIELDS = [
    "bank_name",
    "bank_account_id",
    "bank_transaction_id",
    "bank_date",
    "bank_amount",
    "bank_reference",
    "bank_description",
    "books_status",
    "books_match_status",
    "books_reconciliation_status",
    "analytics_match_count",
    "analytics_customer_ids",
    "analytics_customer_names",
    "analytics_bank_transaction_ids",
    "analytics_references",
    "analytics_search_keys",
    "raw",
]


CREATOR_EXPORT_FIELDS = [
    "creator_payment_id",
    "creator_date",
    "creator_amount",
    "creator_customer_id",
    "creator_customer_name",
    "creator_reference",
    "raw",
]


REFERENCE_DATE_AMOUNT_MATCH_FIELDS = [
    "match_status",
    "match_reason",
    "matched_reference",
    "matched_reference_source",
    "creator_payment_id",
    "creator_date",
    "creator_amount",
    "creator_customer_id",
    "creator_customer_name",
    "creator_reference",
    "bank_name",
    "bank_account_id",
    "bank_transaction_id",
    "bank_date",
    "bank_amount",
    "bank_reference",
    "bank_description",
    "analytics_customer_ids",
    "analytics_customer_names",
    "analytics_references",
    "analytics_search_keys",
]


def _date_to_csv(value: Optional[date]) -> str:
    return value.isoformat() if value else ""


def _parse_date_only(value: Any) -> Optional[date]:
    """Normalize supported date-like values without leaking a datetime."""
    parsed = parse_date(value)
    return parsed.date() if isinstance(parsed, datetime) else parsed


def _reference_tokens(value: str) -> List[str]:
    return [
        _norm_text(token)
        for token in re.split(r"[^A-Za-z0-9]+", str(value or ""))
        if _norm_text(token)
    ]


def _match_to_csv_row(status: str, match: PaymentMatch) -> Dict[str, Any]:
    payment = match.creator_payment
    bank_line = match.bank_statement_line
    analytics = match.analytics_customer
    return {
        "status": status,
        "confidence": match.confidence,
        "reason": match.reason,
        "creator_payment_id": payment.id,
        "creator_date": _date_to_csv(payment.date),
        "creator_amount": payment.amount,
        "creator_customer_id": payment.customer_id,
        "creator_customer_name": payment.customer_name,
        "creator_reference": payment.reference,
        "bank_transaction_id": bank_line.id,
        "bank_account_id": bank_line.bank_account_id,
        "bank_name": bank_line.bank_name,
        "bank_date": _date_to_csv(bank_line.date),
        "bank_amount": bank_line.amount,
        "bank_reference": bank_line.reference,
        "bank_description": bank_line.description,
        "analytics_customer_id": analytics.customer_id,
        "analytics_customer_name": analytics.customer_name,
        "analytics_bank_transaction_id": analytics.bank_transaction_id,
        "analytics_reference": analytics.reference,
        "analytics_search_key": analytics.search_key,
    }


def _creator_to_csv_row(status: str, payment: CreatorPayment) -> Dict[str, Any]:
    row = {field: "" for field in CSV_FIELDS}
    row.update({
        "status": status,
        "creator_payment_id": payment.id,
        "creator_date": _date_to_csv(payment.date),
        "creator_amount": payment.amount,
        "creator_customer_id": payment.customer_id,
        "creator_customer_name": payment.customer_name,
        "creator_reference": payment.reference,
    })
    return row


def _bank_to_csv_row(status: str, bank_line: BankStatementLine) -> Dict[str, Any]:
    row = {field: "" for field in CSV_FIELDS}
    row.update({
        "status": status,
        "bank_transaction_id": bank_line.id,
        "bank_account_id": bank_line.bank_account_id,
        "bank_name": bank_line.bank_name,
        "bank_date": _date_to_csv(bank_line.date),
        "bank_amount": bank_line.amount,
        "bank_reference": bank_line.reference,
        "bank_description": bank_line.description,
    })
    return row


def normalize_creator_payment(record: Dict[str, Any]) -> CreatorPayment:
    customer = _first(record, ("Customer_Name", "customer_name", "Customer", "customer"), {})
    if isinstance(customer, dict):
        customer_id = str(_first(customer, ("ID", "id", "customer_id")))
        customer_name = str(_first(customer, ("Name", "name", "zc_display_value")))
    else:
        customer_id = str(_first(record, ("Customer_ID", "customer_id", "CustomerId", "Books_Customer_ID")))
        customer_name = str(customer)
    return CreatorPayment(
        id=str(_first(record, ("ID", "id", "record_id", "payment_id"))),
        date=_parse_date_only(_first(record, ("Payment_Date", "payment_date", "Date", "date"))),
        amount=_to_float(_first(record, ("Amount", "amount", "Payment_Amount", "payment_amount"))),
        customer_id=customer_id,
        reference=str(_first(record, ("Reference", "reference", "Reference_Number", "reference_number", "UTR", "utr"))),
        customer_name=customer_name,
        raw=record,
    )


def normalize_bank_statement_line(record: Dict[str, Any], bank_account_id: str = "", bank_name: str = "") -> BankStatementLine:
    tx_id = _first(record, ("transaction_id", "id", "banktransaction_id", "statement_line_id"))
    amount = get_abs_amount(record)
    if amount == 0.0:
        amount = abs(_to_float(_first(record, ("amount", "Amount", "deposit", "credit"))))
    return BankStatementLine(
        id=str(tx_id),
        date=_parse_date_only(_first(record, ("date", "Date", "transaction_date"))),
        amount=amount,
        description=str(_first(record, ("description", "Description", "payee", "Payee", "details", "Details"))),
        reference=str(_first(record, ("reference_number", "reference", "cheque_number", "Reference", "UTR", "utr"))),
        bank_account_id=str(_first(record, ("account_id", "bank_account_id"), bank_account_id)),
        bank_name=bank_name,
        raw=record,
    )


def normalize_analytics_customer(record: Dict[str, Any]) -> AnalyticsCustomer:
    return AnalyticsCustomer(
        customer_id=str(_first(record, ("customer_id", "Customer_ID", "Books_Customer_ID", "CustomerId"))),
        bank_transaction_id=str(_first(record, ("bank_transaction_id", "transaction_id", "statement_line_id", "Transaction#"))),
        reference=str(_first(record, ("reference", "Reference", "reference_number", "Reference Number", "UTR", "utr"))),
        search_key=str(_first(record, ("search_key", "Search_Key", "narration_key", "Narration_Key", "description", "Description"))),
        customer_name=str(_first(record, ("customer_name", "Customer_Name", "Customer Name", "Customer"))),
        raw=record,
    )


def fetch_creator_payments(creator_client: Any, config: PaymentReconciliationConfig) -> List[CreatorPayment]:
    if not config.creator_app_link_name or not config.creator_report_link_name:
        raise ValueError("Creator app and report link names are required.")
    records = creator_client.get_all_records(
        config.creator_app_link_name,
        config.creator_report_link_name,
        criteria=config.creator_criteria,
    )
    return [normalize_creator_payment(record) for record in records]


def fetch_bank_statement_lines(
    books_client: Any,
    config: PaymentReconciliationConfig,
    filter_by: str = "",
) -> List[BankStatementLine]:
    lines: List[BankStatementLine] = []
    for account_id in config.bank_account_ids:
        params: Dict[str, Any] = {"account_id": account_id}
        if filter_by:
            params["filter_by"] = filter_by
        if config.start_date:
            params["from_date"] = (config.start_date - timedelta(days=config.date_tolerance_days)).strftime("%Y-%m-%d")
        if config.end_date:
            params["to_date"] = (config.end_date + timedelta(days=config.date_tolerance_days)).strftime("%Y-%m-%d")
        transactions = books_client.bank_transactions.list_all(params=params)
        deposits = [tx for tx in transactions if is_deposit_books_bank_transaction(tx)]
        bank_name = config.bank_account_names.get(account_id, "")
        lines.extend(normalize_bank_statement_line(tx, bank_account_id=account_id, bank_name=bank_name) for tx in deposits)
    return lines


def is_deposit_books_bank_transaction(record: Dict[str, Any]) -> bool:
    """Return whether a Books bank transaction is an incoming bank deposit.

    Zoho Books exposes bank accounts using ledger orientation: a debit increases
    the bank asset and a credit decreases it. This is the opposite of the labels
    commonly shown to a customer on a bank statement.
    """
    direction = str(record.get("debit_or_credit", "")).strip().lower()
    if direction == "debit":
        return True
    if direction == "credit":
        return False

    transaction_type = _norm_text(_first(record, ("transaction_type", "type")))
    if transaction_type in {"deposit", "income", "customerpayment", "sales"}:
        return True
    if transaction_type in {"expense", "withdrawal", "payment", "vendorpayment"}:
        return False

    # Some API/test records omit direction. Keep them available for matching;
    # amount, date, reference, and customer checks still gate confirmation.
    return True


def _books_status_value(record: Dict[str, Any], names: Sequence[str]) -> str:
    return str(_first(record, names)).strip()


def is_unmatched_books_bank_transaction(record: Dict[str, Any]) -> bool:
    explicit_false_fields = (
        "is_matched",
        "is_reconciled",
        "matched",
        "reconciled",
        "is_categorized",
    )
    for field_name in explicit_false_fields:
        if field_name in record:
            value = record.get(field_name)
            if isinstance(value, bool):
                return not value
            if str(value).strip().lower() in {"false", "0", "no"}:
                return True
            if str(value).strip().lower() in {"true", "1", "yes"}:
                return False

    status = _books_status_value(record, ("status", "transaction_status", "match_status", "reconciliation_status"))
    normalized_status = _norm_text(status)
    if normalized_status:
        unmatched_markers = {
            "unmatched",
            "uncategorized",
            "unreconciled",
            "open",
            "imported",
            "notmatched",
            "notreconciled",
        }
        matched_markers = {
            "matched",
            "categorized",
            "reconciled",
            "closed",
        }
        if normalized_status in unmatched_markers:
            return True
        if normalized_status in matched_markers:
            return False

    return True


def fetch_unmatched_bank_statement_lines(books_client: Any, config: PaymentReconciliationConfig) -> List[BankStatementLine]:
    return [
        line
        for line in fetch_bank_statement_lines(books_client, config, filter_by="Status.Uncategorized")
        if is_unmatched_books_bank_transaction(line.raw)
    ]


def fetch_analytics_customer_table(
    analytics_token: str,
    config: PaymentReconciliationConfig,
    domain: str = Config.DOMAIN,
) -> List[AnalyticsCustomer]:
    if not config.analytics_workspace_id or not config.analytics_view_id:
        raise ValueError("Analytics workspace and view IDs are required.")
    client = ZohoAnalyticsAPI(
        access_token=analytics_token,
        organization_id=Config.PAYMENT_ANALYTICS_ORG_ID,
        domain=domain,
    )
    rows = client.views.export_all(config.analytics_workspace_id, config.analytics_view_id)
    return [normalize_analytics_customer(row) for row in rows]


def fetch_analytics_customer_table_bulk(
    analytics_token: str,
    config: PaymentReconciliationConfig,
    domain: str = Config.DOMAIN,
    poll_attempts: int = 12,
    poll_interval_seconds: float = 2.0,
) -> List[AnalyticsCustomer]:
    client = ZohoAnalyticsAPI(
        access_token=analytics_token,
        organization_id=Config.PAYMENT_ANALYTICS_ORG_ID,
        domain=domain,
    )
    rows = client.views.export_bulk(
        config.analytics_workspace_id,
        config.analytics_view_id,
        poll_interval=poll_interval_seconds,
        max_attempts=poll_attempts,
    )
    return [normalize_analytics_customer(row) for row in rows]


def fetch_payment_reconciliation_data(
    creator_client: Any,
    books_client: Any,
    analytics_token: str,
    config: PaymentReconciliationConfig,
) -> Tuple[List[CreatorPayment], List[BankStatementLine], List[AnalyticsCustomer]]:
    return (
        fetch_creator_payments(creator_client, config),
        fetch_unmatched_bank_statement_lines(books_client, config),
        fetch_analytics_customer_table(analytics_token, config),
    )


def _analytics_candidates(bank_line: BankStatementLine, analytics_rows: Sequence[AnalyticsCustomer]) -> List[AnalyticsCustomer]:
    ref = _norm_text(bank_line.reference)
    desc = _norm_text(bank_line.description)
    candidates = []
    for row in analytics_rows:
        if bank_line.id and row.bank_transaction_id and bank_line.id == row.bank_transaction_id:
            candidates.append(row)
            continue
        if _contains_or_equals(_norm_text(row.reference), ref):
            candidates.append(row)
            continue
        if _contains_or_equals(_norm_text(row.search_key), desc):
            candidates.append(row)
    return candidates


ANALYTICS_SEARCH_STOP_TOKENS = {
    "sri",
    "bharath",
    "barath",
    "electrical",
    "electricals",
    "sribharath",
    "sribharathelectricals",
    "bharathelectricals",
    "barathdistributors",
    "payment",
    "transfer",
    "pending",
    "amount",
    "purchase",
    "neft",
    "rtgs",
    "imps",
    "upi",
    "cash",
    "deposit",
    "thillai",
    "nagar",
}


def _looks_like_ifsc(token: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{4}0[a-z0-9]{6}", token))


def _is_searchable_identifier(value: str, min_length: int = 8) -> bool:
    if len(value) < min_length:
        return False
    if value in ANALYTICS_SEARCH_STOP_TOKENS or _looks_like_ifsc(value):
        return False
    if re.fullmatch(r"0+\d{0,3}", value):
        return False
    return any(char.isdigit() for char in value)


def _search_tokens(*values: str, min_length: int = 8) -> List[str]:
    tokens: List[str] = []
    for value in values:
        for handle in re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9._-]+", str(value or "")):
            normalized_handle = _norm_text(handle)
            if len(normalized_handle) >= min_length and normalized_handle not in ANALYTICS_SEARCH_STOP_TOKENS:
                tokens.append(normalized_handle)
        for token in re.split(r"[^A-Za-z0-9]+", str(value or "")):
            normalized = _norm_text(token)
            if _is_searchable_identifier(normalized, min_length=min_length):
                tokens.append(normalized)
    return list(dict.fromkeys(tokens))


def analytics_search_matches_for_bank_line(
    bank_line: BankStatementLine,
    analytics_rows: Sequence[AnalyticsCustomer],
) -> List[AnalyticsCustomer]:
    matches: List[AnalyticsCustomer] = []
    seen_keys = set()
    bank_ref = _norm_text(bank_line.reference)
    if not _is_searchable_identifier(bank_ref):
        bank_ref = ""
    tokens = _search_tokens(bank_line.reference, bank_line.description)

    for row in analytics_rows:
        row_values = [
            _norm_text(row.bank_transaction_id),
            _norm_text(row.reference),
            _norm_text(row.search_key),
            _norm_text(row.customer_id),
            _norm_text(row.customer_name),
        ]
        has_match = False
        if bank_line.id and row.bank_transaction_id and bank_line.id == row.bank_transaction_id:
            has_match = True
        elif bank_ref and any(_contains_or_equals(bank_ref, value) for value in row_values):
            has_match = True
        elif tokens and any(token in value for token in tokens for value in row_values if value):
            has_match = True

        if not has_match:
            continue

        key = (
            row.customer_id,
            row.bank_transaction_id,
            row.reference,
            row.search_key,
            row.customer_name,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        matches.append(row)

    return matches


def _reference_matches(payment: CreatorPayment, bank_line: BankStatementLine, analytics_row: AnalyticsCustomer) -> bool:
    payment_ref = _norm_text(payment.reference)
    if payment_ref:
        reference_values = (
            bank_line.reference,
            bank_line.description,
            analytics_row.reference,
            analytics_row.search_key,
        )
        return any(
            _contains_or_equals(payment_ref, _norm_text(value))
            for value in reference_values
        )
    return bool(analytics_row.bank_transaction_id and analytics_row.bank_transaction_id == bank_line.id)


def _customer_matches(payment: CreatorPayment, analytics_row: AnalyticsCustomer) -> bool:
    if payment.customer_id and analytics_row.customer_id:
        return payment.customer_id == analytics_row.customer_id
    return bool(payment.customer_name and analytics_row.customer_name and _norm_text(payment.customer_name) == _norm_text(analytics_row.customer_name))


def find_exact_payment_matches(
    creator_payments: Sequence[CreatorPayment],
    bank_statement_lines: Sequence[BankStatementLine],
    analytics_rows: Sequence[AnalyticsCustomer],
    date_tolerance_days: int = 0,
) -> Tuple[List[PaymentMatch], List[Dict[str, Any]], List[CreatorPayment], List[BankStatementLine]]:
    matched_creator_ids = set()
    matched_bank_indexes = set()
    exact_matches: List[PaymentMatch] = []
    ambiguous_matches: List[Dict[str, Any]] = []
    candidates_by_bank: List[List[PaymentMatch]] = []

    for bank_line in bank_statement_lines:
        if not bank_line.id or not bank_line.date:
            candidates_by_bank.append([])
            continue
        candidates: List[PaymentMatch] = []
        for analytics_row in _analytics_candidates(bank_line, analytics_rows):
            for payment in creator_payments:
                if not payment.id or not payment.date:
                    continue
                if not _customer_matches(payment, analytics_row):
                    continue
                if _norm_amount(payment.amount) != _norm_amount(bank_line.amount):
                    continue
                if abs((payment.date - bank_line.date).days) > date_tolerance_days:
                    continue
                if not _reference_matches(payment, bank_line, analytics_row):
                    continue
                candidates.append(PaymentMatch(payment, bank_line, analytics_row))

        unique_candidates: Dict[Tuple[str, str, str], PaymentMatch] = {}
        for candidate in candidates:
            key = (
                candidate.creator_payment.id,
                candidate.bank_statement_line.id,
                candidate.analytics_customer.customer_id,
            )
            unique_candidates.setdefault(key, candidate)
        candidates_by_bank.append(list(unique_candidates.values()))

    # A match is safe to confirm only when it is unique from both directions.
    # Resolving rows greedily makes the result depend on bank-line order and can
    # silently confirm the first of two statement lines against one payment.
    creator_bank_indexes: Dict[str, set] = {}
    for bank_index, candidates in enumerate(candidates_by_bank):
        for candidate in candidates:
            creator_bank_indexes.setdefault(candidate.creator_payment.id, set()).add(bank_index)

    for bank_index, (bank_line, unique_candidates) in enumerate(zip(bank_statement_lines, candidates_by_bank)):
        unique_keys = {
            (candidate.creator_payment.id, candidate.bank_statement_line.id, candidate.analytics_customer.customer_id)
            for candidate in unique_candidates
        }
        if len(unique_keys) == 1:
            match = unique_candidates[0]
            competing_bank_indexes = creator_bank_indexes.get(match.creator_payment.id, set())
            if len(competing_bank_indexes) == 1:
                exact_matches.append(match)
                matched_creator_ids.add(match.creator_payment.id)
                matched_bank_indexes.add(bank_index)
                continue

            ambiguous_matches.append({
                "bank_statement_line": bank_line,
                "candidate_count": len(unique_keys),
                "candidates": unique_candidates,
                "reason": "creator payment also matches another bank statement line",
            })
        elif unique_candidates:
            ambiguous_matches.append({
                "bank_statement_line": bank_line,
                "candidate_count": len(unique_keys),
                "candidates": unique_candidates,
                "reason": "bank statement line has multiple candidate matches",
            })

    unmatched_creator = [p for p in creator_payments if p.id not in matched_creator_ids]
    unmatched_bank = [b for index, b in enumerate(bank_statement_lines) if index not in matched_bank_indexes]
    return exact_matches, ambiguous_matches, unmatched_creator, unmatched_bank


def build_books_match_payload(match: PaymentMatch) -> Dict[str, Any]:
    return {
        "transactions": [
            {
                "transaction_id": match.creator_payment.id,
                "transaction_type": "customer_payment",
                "amount": match.creator_payment.amount,
            }
        ]
    }


def confirm_payment_matches(
    books_client: Any,
    matches: Sequence[PaymentMatch],
    dry_run: bool = True,
    payload_builder: Callable[[PaymentMatch], Dict[str, Any]] = build_books_match_payload,
) -> Tuple[List[PaymentMatch], List[Dict[str, Any]]]:
    confirmed: List[PaymentMatch] = []
    responses: List[Dict[str, Any]] = []
    for match in matches:
        payload = payload_builder(match)
        if dry_run:
            responses.append({
                "dry_run": True,
                "bank_transaction_id": match.bank_statement_line.id,
                "payload": payload,
            })
            continue
        response = books_client.bank_transactions.match(match.bank_statement_line.id, payload)
        responses.append(response)
        response_code = response.get("code") if isinstance(response, dict) else None
        if response_code is None or str(response_code).strip() == "0":
            confirmed.append(match)
        else:
            logger.warning(
                "Books rejected payment match for bank transaction %s: %s",
                match.bank_statement_line.id,
                response,
            )
    return confirmed, responses


def payment_reconciliation_rows(result: PaymentReconciliationResult) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    confirmed_ids = {
        (match.creator_payment.id, match.bank_statement_line.id)
        for match in result.confirmed_matches
    }

    for match in result.exact_matches:
        status = "confirmed_match" if (match.creator_payment.id, match.bank_statement_line.id) in confirmed_ids else "exact_match"
        rows.append(_match_to_csv_row(status, match))

    for ambiguous in result.ambiguous_matches:
        for candidate in ambiguous.get("candidates", []):
            rows.append(_match_to_csv_row("ambiguous_candidate", candidate))

    for payment in result.unmatched_creator_payments:
        rows.append(_creator_to_csv_row("unmatched_creator_payment", payment))

    for bank_line in result.unmatched_bank_statement_lines:
        rows.append(_bank_to_csv_row("unmatched_bank_statement_line", bank_line))

    return rows


def write_payment_reconciliation_csv(result: PaymentReconciliationResult, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = payment_reconciliation_rows(result)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _joined(values: Sequence[str]) -> str:
    return " | ".join(value for value in values if value)


def unmatched_bank_statement_export_rows(
    bank_lines: Sequence[BankStatementLine],
    analytics_rows: Sequence[AnalyticsCustomer],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for bank_line in bank_lines:
        analytics_matches = analytics_search_matches_for_bank_line(bank_line, analytics_rows)
        raw = bank_line.raw
        rows.append({
            "bank_name": bank_line.bank_name,
            "bank_account_id": bank_line.bank_account_id,
            "bank_transaction_id": bank_line.id,
            "bank_date": _date_to_csv(bank_line.date),
            "bank_amount": bank_line.amount,
            "bank_reference": bank_line.reference,
            "bank_description": bank_line.description,
            "books_status": _books_status_value(raw, ("status", "transaction_status")),
            "books_match_status": _books_status_value(raw, ("match_status", "is_matched", "matched", "is_categorized")),
            "books_reconciliation_status": _books_status_value(raw, ("reconciliation_status", "is_reconciled", "reconciled")),
            "analytics_match_count": len(analytics_matches),
            "analytics_customer_ids": _joined([row.customer_id for row in analytics_matches]),
            "analytics_customer_names": _joined([row.customer_name for row in analytics_matches]),
            "analytics_bank_transaction_ids": _joined([row.bank_transaction_id for row in analytics_matches]),
            "analytics_references": _joined([row.reference for row in analytics_matches]),
            "analytics_search_keys": _joined([row.search_key for row in analytics_matches]),
            "raw": _compact_json(raw),
        })
    return rows


def creator_payment_export_rows(creator_payments: Sequence[CreatorPayment]) -> List[Dict[str, Any]]:
    return [
        {
            "creator_payment_id": payment.id,
            "creator_date": _date_to_csv(payment.date),
            "creator_amount": payment.amount,
            "creator_customer_id": payment.customer_id,
            "creator_customer_name": payment.customer_name,
            "creator_reference": payment.reference,
            "raw": _compact_json(payment.raw),
        }
        for payment in creator_payments
    ]


def _write_csv(output_path: str, fields: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def write_unmatched_bank_statement_csv(
    bank_lines: Sequence[BankStatementLine],
    analytics_rows: Sequence[AnalyticsCustomer],
    output_path: str,
) -> str:
    return _write_csv(
        output_path,
        UNMATCHED_BANK_EXPORT_FIELDS,
        unmatched_bank_statement_export_rows(bank_lines, analytics_rows),
    )


def write_creator_payments_csv(
    creator_payments: Sequence[CreatorPayment],
    output_path: str,
) -> str:
    return _write_csv(
        output_path,
        CREATOR_EXPORT_FIELDS,
        creator_payment_export_rows(creator_payments),
    )


def _reference_match_source(payment: CreatorPayment, bank_line: BankStatementLine, analytics_rows: Sequence[AnalyticsCustomer]) -> Tuple[str, str]:
    payment_ref = _norm_text(payment.reference)
    if not payment_ref:
        return "", ""

    reference_sources = [
        ("bank_reference", bank_line.reference),
        ("bank_description", bank_line.description),
    ]
    for row in analytics_rows:
        reference_sources.extend([
            ("analytics_reference", row.reference),
            ("analytics_search_key", row.search_key),
        ])

    for source, value in reference_sources:
        normalized_value = _norm_text(value)
        if (
            payment_ref in _reference_tokens(value)
            or (len(payment_ref) >= 4 and _contains_or_equals(payment_ref, normalized_value))
        ):
            return str(payment.reference), source
    return "", ""


def reference_date_amount_match_rows(
    creator_payments: Sequence[CreatorPayment],
    bank_lines: Sequence[BankStatementLine],
    analytics_rows: Sequence[AnalyticsCustomer],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for bank_line in bank_lines:
        if not bank_line.date:
            continue
        analytics_matches = analytics_search_matches_for_bank_line(bank_line, analytics_rows)
        for payment in creator_payments:
            if not payment.date:
                continue
            if payment.date != bank_line.date:
                continue
            if _norm_amount(payment.amount) != _norm_amount(bank_line.amount):
                continue

            matched_reference, matched_reference_source = _reference_match_source(
                payment,
                bank_line,
                analytics_matches,
            )
            if not matched_reference:
                continue

            rows.append({
                "match_status": "reference_date_amount_match",
                "match_reason": "creator reference matched the normalized bank/analytics reference; date and amount are equal",
                "matched_reference": matched_reference,
                "matched_reference_source": matched_reference_source,
                "creator_payment_id": payment.id,
                "creator_date": _date_to_csv(payment.date),
                "creator_amount": payment.amount,
                "creator_customer_id": payment.customer_id,
                "creator_customer_name": payment.customer_name,
                "creator_reference": payment.reference,
                "bank_name": bank_line.bank_name,
                "bank_account_id": bank_line.bank_account_id,
                "bank_transaction_id": bank_line.id,
                "bank_date": _date_to_csv(bank_line.date),
                "bank_amount": bank_line.amount,
                "bank_reference": bank_line.reference,
                "bank_description": bank_line.description,
                "analytics_customer_ids": _joined([row.customer_id for row in analytics_matches]),
                "analytics_customer_names": _joined([row.customer_name for row in analytics_matches]),
                "analytics_references": _joined([row.reference for row in analytics_matches]),
                "analytics_search_keys": _joined([row.search_key for row in analytics_matches]),
            })
    return rows


def write_reference_date_amount_matches_csv(
    creator_payments: Sequence[CreatorPayment],
    bank_lines: Sequence[BankStatementLine],
    analytics_rows: Sequence[AnalyticsCustomer],
    output_path: str,
) -> str:
    return _write_csv(
        output_path,
        REFERENCE_DATE_AMOUNT_MATCH_FIELDS,
        reference_date_amount_match_rows(creator_payments, bank_lines, analytics_rows),
    )


def reconcile_and_confirm_payments(
    creator_client: Any,
    books_client: Any,
    analytics_token: str,
    config: PaymentReconciliationConfig,
) -> PaymentReconciliationResult:
    creator_payments, bank_lines, analytics_rows = fetch_payment_reconciliation_data(
        creator_client,
        books_client,
        analytics_token,
        config,
    )
    matches, ambiguous, unmatched_creator, unmatched_bank = find_exact_payment_matches(
        creator_payments,
        bank_lines,
        analytics_rows,
        date_tolerance_days=config.date_tolerance_days,
    )
    confirmed, responses = confirm_payment_matches(
        books_client,
        matches,
        dry_run=config.confirm_dry_run,
    )
    logger.info(
        "Payment reconciliation: %s exact, %s confirmed, %s ambiguous",
        len(matches),
        len(confirmed),
        len(ambiguous),
    )
    return PaymentReconciliationResult(
        exact_matches=matches,
        confirmed_matches=confirmed,
        confirmation_responses=responses,
        ambiguous_matches=ambiguous,
        unmatched_creator_payments=unmatched_creator,
        unmatched_bank_statement_lines=unmatched_bank,
    )
