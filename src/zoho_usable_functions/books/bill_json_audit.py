"""Compare structured invoice JSON with a Zoho Books bill."""

from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Optional

from zoho_usable_functions.inventory.name_sku_audit import normalize_name_or_sku


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> str:
    raw = _text(value)
    for date_format in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(raw, date_format).date().isoformat()
        except ValueError:
            continue
    return raw


def normalize_invoice_json(invoice_json: dict[str, Any]) -> dict[str, Any]:
    """Normalize supported Gemini invoice schemas into one comparison shape."""
    if "invoice_details" in invoice_json:
        details = invoice_json.get("invoice_details", {})
        source_totals = invoice_json.get("totals", {})
        subtotal = _number(source_totals.get("subtotal"))
        discount = _number(source_totals.get("discount")) or 0.0
        return {
            "inv": {
                "no": details.get("invoice_number"),
                "date": details.get("invoice_date"),
                "taxable": subtotal + discount if subtotal is not None else None,
            },
            "items": [
                {
                    "sku": line.get("sku"),
                    "name": line.get("item_description"),
                    "hsn": line.get("hsn_sac"),
                    "qty": line.get("shipped_qty"),
                    "unit": line.get("unit"),
                    "rate": line.get("rate"),
                    "amount": line.get("amount"),
                }
                for line in invoice_json.get("line_items", [])
            ],
            "totals": {
                "subtotal": source_totals.get("subtotal"),
                "discount": discount,
                "tax": source_totals.get("igst_amount"),
                "round_off": source_totals.get("round_off"),
                "net": source_totals.get("total_amount"),
            },
        }

    invoice = invoice_json.get("inv", {})
    items = []
    for line in invoice_json.get("items", []):
        total = _number(line.get("total"))
        tax = _number(line.get("gst"))
        amount = total - tax if total is not None and tax is not None else None
        items.append(
            {
                **line,
                "rate": line.get("billed_net_rate"),
                "amount": amount,
            }
        )
    subtotal = sum(_number(line.get("amount")) or 0.0 for line in items)
    taxable = _number(invoice.get("taxable"))
    source_totals = invoice_json.get("totals", {})
    return {
        "inv": invoice,
        "items": items,
        "totals": {
            "subtotal": subtotal,
            "discount": taxable - subtotal if taxable is not None else None,
            "tax": source_totals.get("tax"),
            "round_off": source_totals.get("round_off"),
            "net": source_totals.get("net"),
        },
    }


def find_bill_by_number(books_client: Any, bill_number: str) -> Optional[dict[str, Any]]:
    """Find and retrieve one bill whose number or reference exactly matches."""
    response = books_client.bills.list(params={"bill_number": bill_number})
    candidates = response.get("bills", [])
    needle = _text(bill_number).casefold()
    exact = [
        bill
        for bill in candidates
        if needle
        in {
            _text(bill.get("bill_number")).casefold(),
            _text(bill.get("reference_number")).casefold(),
        }
    ]
    if not exact:
        return None
    if len(exact) > 1:
        ids = ", ".join(_text(bill.get("bill_id")) for bill in exact)
        raise ValueError(f"Multiple Zoho bills match {bill_number!r}: {ids}")
    bill_id = exact[0].get("bill_id") or exact[0].get("id")
    detail = books_client.bills.get(bill_id)
    return detail.get("bill", detail)


def _line_similarity(json_line: dict[str, Any], zoho_line: dict[str, Any]) -> tuple[float, str]:
    json_sku = normalize_name_or_sku(json_line.get("sku"))
    zoho_sku = normalize_name_or_sku(zoho_line.get("sku"))
    if json_sku and zoho_sku and json_sku == zoho_sku:
        return 1.0, "sku"

    json_name = normalize_name_or_sku(json_line.get("name"))
    zoho_name = normalize_name_or_sku(zoho_line.get("name") or zoho_line.get("item_name"))
    if json_name and zoho_name and json_name == zoho_name:
        return 1.0, "name"
    return SequenceMatcher(None, json_name, zoho_name).ratio(), "fuzzy_name"


def _line_match_score(
    json_line: dict[str, Any],
    zoho_line: dict[str, Any],
) -> tuple[float, float, str]:
    """Score names while strongly preferring matching quantity and rate."""
    name_similarity, method = _line_similarity(json_line, zoho_line)
    score = name_similarity

    json_quantity = _number(json_line.get("qty"))
    zoho_quantity = _number(zoho_line.get("quantity"))
    if json_quantity is not None and zoho_quantity is not None:
        score += 0.35 if abs(json_quantity - zoho_quantity) <= 0.001 else -0.35

    json_rate = _number(json_line.get("rate"))
    zoho_rate = _number(zoho_line.get("rate"))
    if json_rate is not None and zoho_rate is not None:
        score += 0.45 if abs(json_rate - zoho_rate) <= 0.01 else -0.45

    json_hsn = normalize_name_or_sku(json_line.get("hsn"))
    zoho_hsn = normalize_name_or_sku(zoho_line.get("hsn_or_sac"))
    if json_hsn and zoho_hsn and json_hsn == zoho_hsn:
        score += 0.10

    if score > name_similarity:
        method = "structured_name"
    return score, name_similarity, method


def match_bill_lines(
    json_lines: list[dict[str, Any]],
    zoho_lines: list[dict[str, Any]],
    minimum_similarity: float = 0.60,
) -> list[tuple[dict[str, Any], Optional[dict[str, Any]], float, str]]:
    """Greedily match each JSON line to one unique Zoho line."""
    unused = set(range(len(zoho_lines)))
    matches = []
    for json_line in json_lines:
        ranked = sorted(
            (
                (*_line_match_score(json_line, zoho_lines[index]), index)
                for index in unused
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < minimum_similarity:
            matches.append((json_line, None, ranked[0][1] if ranked else 0.0, "unmatched"))
            continue
        _, similarity, method, index = ranked[0]
        unused.remove(index)
        matches.append((json_line, zoho_lines[index], similarity, method))
    return matches


def _comparison(label: str, json_value: Any, zoho_value: Any, tolerance: float = 0.0) -> dict[str, Any]:
    json_number = _number(json_value)
    zoho_number = _number(zoho_value)
    if json_number is not None and zoho_number is not None:
        difference = round(zoho_number - json_number, 4)
        matches = abs(difference) <= tolerance
    else:
        difference = None
        matches = _text(json_value).casefold() == _text(zoho_value).casefold()
    return {
        "field": label,
        "json": json_value,
        "zoho": zoho_value,
        "difference": difference,
        "matches": matches,
    }


def _zoho_line_taxable(line: dict[str, Any]) -> Any:
    for key in ("item_total", "taxable_amount", "line_item_total", "amount"):
        if line.get(key) is not None:
            return line[key]
    quantity = _number(line.get("quantity"))
    rate = _number(line.get("rate"))
    return quantity * rate if quantity is not None and rate is not None else None


def _zoho_line_tax(line: dict[str, Any]) -> Any:
    for key in ("tax_amount", "tax", "line_item_tax"):
        if line.get(key) is not None:
            return line[key]
    line_taxes = line.get("line_item_taxes")
    if isinstance(line_taxes, list) and line_taxes:
        amounts = [_number(tax.get("tax_amount")) for tax in line_taxes]
        return sum(amount for amount in amounts if amount is not None)
    return None


def _zoho_line_total(line: dict[str, Any]) -> Any:
    if line.get("total") is not None:
        return line["total"]
    taxable = _number(_zoho_line_taxable(line))
    tax = _number(_zoho_line_tax(line))
    return taxable + tax if taxable is not None and tax is not None else taxable


def compare_invoice_json_to_bill(
    invoice_json: dict[str, Any],
    bill: dict[str, Any],
    amount_tolerance: float = 0.05,
    minimum_similarity: float = 0.60,
) -> dict[str, Any]:
    """Build a field-by-field and line-by-line audit report."""
    invoice_json = normalize_invoice_json(invoice_json)
    invoice = invoice_json.get("inv", {})
    totals = invoice_json.get("totals", {})
    json_lines = invoice_json.get("items", [])
    json_extended_subtotal = sum(
        (_number(line.get("qty")) or 0.0) * (_number(line.get("rate")) or 0.0)
        for line in json_lines
    )
    json_line_amount_total = sum(_number(line.get("amount")) or 0.0 for line in json_lines)
    has_line_tax = any(line.get("gst") is not None for line in json_lines)
    has_line_total = any(line.get("total") is not None for line in json_lines)
    json_line_tax_total = sum(_number(line.get("gst")) or 0.0 for line in json_lines) if has_line_tax else None
    json_line_grand_total = (
        sum(_number(line.get("total")) or 0.0 for line in json_lines) if has_line_total else None
    )
    stated_subtotal = _number(totals.get("subtotal"))
    stated_discount = _number(totals.get("discount"))
    stated_taxable = _number(invoice.get("taxable"))
    bill_discount = bill.get("discount_amount")
    if bill_discount is None:
        bill_discount = bill.get("discount")
    if bill_discount is None:
        bill_discount = 0.0
    bill_net_taxable = _number(bill.get("sub_total"))
    if bill_net_taxable is not None and bill.get("is_discount_before_tax") and _number(bill_discount) is not None:
        bill_net_taxable -= _number(bill_discount) or 0.0

    header_comparisons = [
        _comparison("invoice_number", invoice.get("no"), bill.get("bill_number") or bill.get("reference_number")),
        _comparison("invoice_date", _date(invoice.get("date")), _date(bill.get("date"))),
        _comparison("subtotal_before_discount", stated_subtotal, bill.get("sub_total"), amount_tolerance),
        _comparison("entity_discount", stated_discount, -abs(_number(bill_discount) or 0.0), amount_tolerance),
        _comparison("taxable_after_discount", invoice.get("taxable"), bill_net_taxable, amount_tolerance),
        _comparison("tax", totals.get("tax"), bill.get("tax_total") or bill.get("tax_amount"), amount_tolerance),
        _comparison("round_off", totals.get("round_off"), bill.get("adjustment"), amount_tolerance),
        _comparison("net", totals.get("net"), bill.get("total"), amount_tolerance),
    ]

    line_results = []
    zoho_lines = bill.get("line_items", [])
    for index, (json_line, zoho_line, similarity, method) in enumerate(
        match_bill_lines(json_lines, zoho_lines, minimum_similarity),
        start=1,
    ):
        if zoho_line is None:
            line_results.append(
                {
                    "json_line": index,
                    "json_name": json_line.get("name"),
                    "json_sku": json_line.get("sku"),
                    "matched": False,
                    "match_method": method,
                    "name_similarity": round(similarity, 4),
                    "comparisons": [],
                    "differences": ["no matching Zoho line"],
                }
            )
            continue

        zoho_taxable = _zoho_line_taxable(zoho_line)
        comparisons = [
            _comparison("sku", json_line.get("sku"), zoho_line.get("sku")) if json_line.get("sku") else None,
            _comparison("hsn", json_line.get("hsn"), zoho_line.get("hsn_or_sac")),
            _comparison("quantity", json_line.get("qty"), zoho_line.get("quantity"), 0.001),
            _comparison("rate", json_line.get("rate"), zoho_line.get("rate"), amount_tolerance),
            _comparison("amount", json_line.get("amount"), zoho_taxable, amount_tolerance),
            (
                _comparison("tax", json_line.get("gst"), _zoho_line_tax(zoho_line), amount_tolerance)
                if json_line.get("gst") is not None
                else None
            ),
            (
                _comparison("total", json_line.get("total"), _zoho_line_total(zoho_line), amount_tolerance)
                if json_line.get("total") is not None
                else None
            ),
        ]
        comparisons = [comparison for comparison in comparisons if comparison is not None]
        differences = [comparison["field"] for comparison in comparisons if not comparison["matches"]]
        line_results.append(
            {
                "json_line": index,
                "json_name": json_line.get("name"),
                "json_sku": json_line.get("sku"),
                "zoho_line_item_id": zoho_line.get("line_item_id"),
                "zoho_name": zoho_line.get("name") or zoho_line.get("item_name"),
                "zoho_sku": zoho_line.get("sku"),
                "matched": True,
                "match_method": method,
                "name_similarity": round(similarity, 4),
                "comparisons": comparisons,
                "differences": differences,
            }
        )

    matched_zoho_ids = {line.get("zoho_line_item_id") for line in line_results if line.get("matched")}
    extra_zoho_lines = [
        {
            "line_item_id": line.get("line_item_id"),
            "name": line.get("name") or line.get("item_name"),
            "sku": line.get("sku"),
        }
        for line in zoho_lines
        if line.get("line_item_id") not in matched_zoho_ids
    ]
    all_header_match = all(comparison["matches"] for comparison in header_comparisons)
    all_lines_match = (
        len(line_results) == len(json_lines)
        and all(line["matched"] and not line["differences"] for line in line_results)
        and not extra_zoho_lines
    )
    return {
        "bill_found": True,
        "bill_id": bill.get("bill_id") or bill.get("id"),
        "bill_number": bill.get("bill_number"),
        "header_comparisons": header_comparisons,
        "source_json_checks": {
            "extended_subtotal_from_quantity_x_rate": round(json_extended_subtotal, 2),
            "sum_of_line_amounts": round(json_line_amount_total, 2),
            "stated_subtotal": stated_subtotal,
            "line_amounts_minus_stated_subtotal": round(json_line_amount_total - (stated_subtotal or 0.0), 2),
            "stated_taxable": stated_taxable,
            "stated_entity_discount": stated_discount,
            "sum_of_line_gst": round(json_line_tax_total, 2) if json_line_tax_total is not None else None,
            "stated_tax": _number(totals.get("tax")),
            "line_gst_minus_stated_tax": (
                round(json_line_tax_total - (_number(totals.get("tax")) or 0.0), 2)
                if json_line_tax_total is not None
                else None
            ),
            "sum_of_line_totals": (
                round(json_line_grand_total, 2) if json_line_grand_total is not None else None
            ),
            "stated_net": _number(totals.get("net")),
            "line_totals_minus_stated_net": (
                round(json_line_grand_total - (_number(totals.get("net")) or 0.0), 2)
                if json_line_grand_total is not None
                else None
            ),
        },
        "line_comparisons": line_results,
        "extra_zoho_lines": extra_zoho_lines,
        "summary": {
            "json_lines": len(json_lines),
            "zoho_lines": len(zoho_lines),
            "matched_lines": sum(1 for line in line_results if line["matched"]),
            "lines_with_differences": sum(1 for line in line_results if line["differences"]),
            "header_matches": all_header_match,
            "lines_match": all_lines_match,
            "overall_match": all_header_match and all_lines_match,
        },
    }


def build_name_sku_mapping(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the concise Gemini-name to Zoho-name/SKU mapping."""
    invoice_number = report.get("bill_number")
    return [
        {
            "invoice_number": invoice_number,
            "json_name": line.get("json_name"),
            "zoho_name": line.get("zoho_name"),
            "zoho_sku": line.get("zoho_sku"),
        }
        for line in report.get("line_comparisons", [])
        if line.get("matched")
    ]


def merge_name_sku_mappings(
    existing: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace updated invoices while retaining every other invoice."""
    updated_invoices = {
        _text(record.get("invoice_number")).casefold()
        for record in updates
    }
    retained = [
        record
        for record in existing
        if _text(record.get("invoice_number")).casefold() not in updated_invoices
    ]
    return retained + updates
