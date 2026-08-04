import logging
from typing import Any, Dict, List, Optional, Union, Sequence, Tuple
from ..core.models import DotDict
from ..core.auth import get_analytics_client
from ..core.config import Config
from ..core.exceptions import ZohoUsableError

logger = logging.getLogger(__name__)


def _escape_sql_literal(val: str) -> str:
    """Escapes single quotes for SQL string literals."""
    return str(val).replace("'", "''")


def build_billed_prices_sql_query(
    customer_id: str,
    skus: Sequence[str],
    view_name: Optional[str] = None,
    custom_where: Optional[str] = None,
) -> str:
    """
    Builds a dynamic SQL SELECT query for Zoho Analytics to fetch historical invoice line items.

    :param customer_id: Customer contact ID or name.
    :param skus: List of SKU codes to query.
    :param view_name: Optional name of a combined view in Zoho Analytics (e.g., 'Invoice Details').
                     If None, defaults to joining 'Invoices' and 'Invoice Items'.
    :param custom_where: Additional SQL WHERE clauses to filter results.
    :return: Formatted SQL query string.
    """
    escaped_customer_id = _escape_sql_literal(customer_id)
    escaped_skus = [_escape_sql_literal(sku) for sku in skus if sku]

    if not escaped_skus:
        raise ValueError("At least one non-empty SKU must be provided.")

    sku_clause = ", ".join(f"'{s}'" for s in escaped_skus)

    if view_name:
        escaped_view = _escape_sql_literal(view_name)
        sql = (
            f'SELECT "Customer ID", "Customer Name", "Invoice Number", "Invoice Date", '
            f'"SKU", "Item Name", "Quantity", "Rate", "Discount" '
            f'FROM "{escaped_view}" '
            f'WHERE ("Customer ID" = \'{escaped_customer_id}\' OR "Customer Name" = \'{escaped_customer_id}\') '
            f'AND "SKU" IN ({sku_clause})'
        )
    else:
        sql = (
            f'SELECT i."Customer ID", i."Customer Name", i."Invoice Number", i."Invoice Date", '
            f'ii."SKU", ii."Item Name", ii."Quantity", ii."Rate", ii."Discount" '
            f'FROM "Invoices" i '
            f'JOIN "Invoice Items" ii ON i."Invoice ID" = ii."Invoice ID" '
            f'WHERE (i."Customer ID" = \'{escaped_customer_id}\' OR i."Customer Name" = \'{escaped_customer_id}\') '
            f'AND i."Status" NOT IN (\'Void\', \'Draft\') '
            f'AND ii."SKU" IN ({sku_clause})'
        )

    if custom_where:
        sql += f" AND ({custom_where})"

    if view_name:
        sql += ' ORDER BY "Invoice Date" DESC'
    else:
        sql += ' ORDER BY i."Invoice Date" DESC'

    return sql


def _normalize_item_input(items: Sequence[Union[Dict[str, Any], Tuple[str, Any], str]]) -> List[Dict[str, Any]]:
    """
    Normalizes diverse item inputs into a consistent list of dicts: [{'sku': str, 'qty': float}].
    """
    normalized = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"sku": item.strip(), "qty": 1.0})
        elif isinstance(item, (tuple, list)):
            sku = str(item[0]).strip() if item else ""
            qty = float(item[1]) if len(item) > 1 else 1.0
            normalized.append({"sku": sku, "qty": qty})
        elif isinstance(item, dict):
            sku = str(item.get("sku") or item.get("item_sku") or item.get("code") or "").strip()
            raw_qty = item.get("qty") if "qty" in item else item.get("quantity", 1.0)
            try:
                qty = float(raw_qty)
            except (ValueError, TypeError):
                qty = 1.0
            normalized.append({"sku": sku, "qty": qty})
        else:
            logger.warning("Unrecognized item input type: %s", type(item))
    return [i for i in normalized if i["sku"]]


def fetch_last_invoiced_prices(
    analytics_client: Any,
    workspace_id: str,
    customer_id: str,
    items: Sequence[Union[Dict[str, Any], Tuple[str, Any], str]],
    view_name: Optional[str] = None,
    poll_interval: float = 2.0,
    max_attempts: int = 12,
) -> List[DotDict]:
    """
    Fetches the last invoiced price for each SKU for a customer via Zoho Analytics.

    :param analytics_client: Instantiated ZohoAnalyticsAPI client.
    :param workspace_id: Zoho Analytics Workspace ID.
    :param customer_id: Customer contact ID or name.
    :param items: List of items, e.g. [{'sku': 'SKU1', 'qty': 5}] or [('SKU1', 5)] or ['SKU1'].
    :param view_name: Optional custom view name in Zoho Analytics.
    :param poll_interval: Polling interval for async export query in seconds.
    :param max_attempts: Maximum polling attempts.
    :return: List of DotDict results containing last billed price details for each requested item.
    """
    norm_items = _normalize_item_input(items)
    if not norm_items:
        logger.warning("No valid SKUs provided to fetch_last_invoiced_prices.")
        return []

    skus = list({item["sku"] for item in norm_items})
    sql = build_billed_prices_sql_query(customer_id=customer_id, skus=skus, view_name=view_name)

    logger.info("Executing Zoho Analytics SQL query for customer %s and %d SKUs.", customer_id, len(skus))
    try:
        query_rows = analytics_client.views.query_data(
            workspace_id=workspace_id,
            sql_query=sql,
            poll_interval=poll_interval,
            max_attempts=max_attempts,
        )
    except Exception as e:
        logger.error("Zoho Analytics query execution failed: %s", e)
        raise ZohoUsableError(f"Failed to query Zoho Analytics for customer billed prices: {e}") from e

    # Group query output by uppercase SKU to pick the newest record for each SKU
    records_by_sku: Dict[str, Dict[str, Any]] = {}
    for row in query_rows:
        # Standardize field names from query result
        sku_val = str(row.get("SKU") or row.get("ii.SKU") or "").strip()
        sku_key = sku_val.upper()

        if not sku_key:
            continue

        # Rows are ordered by Invoice Date DESC, so the first row seen for a SKU is the latest
        if sku_key not in records_by_sku:
            records_by_sku[sku_key] = row

    results: List[DotDict] = []
    for item in norm_items:
        target_sku = item["sku"]
        req_qty = item["qty"]
        matched_row = records_by_sku.get(target_sku.upper())

        if matched_row:
            try:
                rate = float(matched_row.get("Rate") or matched_row.get("ii.Rate") or matched_row.get("Item Price") or 0.0)
            except (ValueError, TypeError):
                rate = 0.0

            try:
                last_qty = float(matched_row.get("Quantity") or matched_row.get("ii.Quantity") or 0.0)
            except (ValueError, TypeError):
                last_qty = 0.0

            try:
                discount = float(matched_row.get("Discount") or matched_row.get("ii.Discount") or 0.0)
            except (ValueError, TypeError):
                discount = 0.0

            inv_number = str(matched_row.get("Invoice Number") or matched_row.get("i.Invoice Number") or "")
            inv_date = str(matched_row.get("Invoice Date") or matched_row.get("i.Invoice Date") or "")
            item_name = str(matched_row.get("Item Name") or matched_row.get("ii.Item Name") or "")

            results.append(
                DotDict({
                    "sku": target_sku,
                    "requested_qty": req_qty,
                    "last_billed_price": rate,
                    "last_billed_qty": last_qty,
                    "last_invoice_number": inv_number,
                    "last_invoice_date": inv_date,
                    "discount": discount,
                    "item_name": item_name,
                    "found": True,
                })
            )
        else:
            results.append(
                DotDict({
                    "sku": target_sku,
                    "requested_qty": req_qty,
                    "last_billed_price": None,
                    "last_billed_qty": None,
                    "last_invoice_number": None,
                    "last_invoice_date": None,
                    "discount": None,
                    "item_name": None,
                    "found": False,
                })
            )

    return results


def get_last_billed_prices_for_customer(
    customer_id: str,
    items: Sequence[Union[Dict[str, Any], Tuple[str, Any], str]],
    workspace_id: Optional[str] = None,
    analytics_token: Optional[str] = None,
    analytics_client: Optional[Any] = None,
    view_name: Optional[str] = None,
) -> DotDict:
    """
    High-level convenience function to fetch last invoiced prices for a customer.
    Auto-initializes the Zoho Analytics API client if not provided.

    :param customer_id: Zoho Books Customer ID or Customer Name.
    :param items: List of items (dicts, tuples, or SKU strings).
    :param workspace_id: Optional Zoho Analytics Workspace ID (defaults to Config.PAYMENT_ANALYTICS_WORKSPACE_ID).
    :param analytics_token: Optional token override.
    :param analytics_client: Optional pre-configured ZohoAnalyticsAPI client.
    :param view_name: Optional custom Analytics view name.
    :return: DotDict summary containing customer_id, workspace_id, found_count, and list of item results.
    """
    ws_id = workspace_id or getattr(Config, "PAYMENT_ANALYTICS_WORKSPACE_ID", "")
    if not ws_id:
        raise ValueError("No Zoho Analytics Workspace ID provided or configured.")

    if analytics_client is None:
        analytics_client = get_analytics_client(token=analytics_token)

    results = fetch_last_invoiced_prices(
        analytics_client=analytics_client,
        workspace_id=ws_id,
        customer_id=customer_id,
        items=items,
        view_name=view_name,
    )

    found_count = sum(1 for item in results if item.get("found"))

    return DotDict({
        "customer_id": customer_id,
        "workspace_id": ws_id,
        "item_count": len(results),
        "found_count": found_count,
        "items": results,
    })
