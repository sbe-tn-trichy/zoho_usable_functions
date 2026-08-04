import unittest
from unittest.mock import MagicMock
from zoho_usable_functions.analytics.billed_prices import (
    build_billed_prices_sql_query,
    fetch_last_invoiced_prices,
    get_last_billed_prices_for_customer,
    _normalize_item_input,
)
from zoho_usable_functions.core.exceptions import ZohoUsableError
from zoho_usable_functions.core.models import DotDict


class TestAnalyticsBilledPrices(unittest.TestCase):
    def test_build_billed_prices_sql_query_default(self):
        sql = build_billed_prices_sql_query(customer_id="CUST123", skus=["SKU-001", "SKU-002"])
        self.assertIn('FROM "Invoices" i', sql)
        self.assertIn('JOIN "Invoice Items" ii', sql)
        self.assertIn("i.\"Customer ID\" = 'CUST123'", sql)
        self.assertIn("'SKU-001', 'SKU-002'", sql)
        self.assertIn('ORDER BY i."Invoice Date" DESC', sql)

    def test_build_billed_prices_sql_query_with_view(self):
        sql = build_billed_prices_sql_query(customer_id="CUST123", skus=["SKU-001"], view_name="Invoice Details")
        self.assertIn('FROM "Invoice Details"', sql)
        self.assertIn('"Customer ID" = \'CUST123\'', sql)
        self.assertIn("'SKU-001'", sql)
        self.assertIn('ORDER BY "Invoice Date" DESC', sql)

    def test_build_billed_prices_sql_query_sql_injection_escaping(self):
        sql = build_billed_prices_sql_query(customer_id="O'Connor", skus=["SKU'X"])
        self.assertIn("O''Connor", sql)
        self.assertIn("SKU''X", sql)

    def test_build_billed_prices_sql_query_empty_skus(self):
        with self.assertRaises(ValueError):
            build_billed_prices_sql_query(customer_id="CUST123", skus=[])

    def test_normalize_item_input(self):
        items = [
            {"sku": "SKU-001", "qty": 10},
            ("SKU-002", 5),
            "SKU-003",
            {"item_sku": "SKU-004", "quantity": "15.5"},
        ]
        norm = _normalize_item_input(items)
        self.assertEqual(len(norm), 4)
        self.assertEqual(norm[0], {"sku": "SKU-001", "qty": 10.0})
        self.assertEqual(norm[1], {"sku": "SKU-002", "qty": 5.0})
        self.assertEqual(norm[2], {"sku": "SKU-003", "qty": 1.0})
        self.assertEqual(norm[3], {"sku": "SKU-004", "qty": 15.5})

    def test_fetch_last_invoiced_prices_success(self):
        mock_client = MagicMock()
        mock_client.views.query_data.return_value = [
            {
                "SKU": "SKU-001",
                "Rate": "150.50",
                "Quantity": "10",
                "Discount": "0.0",
                "Invoice Number": "INV-1001",
                "Invoice Date": "2026-07-20",
                "Item Name": "Test Item 1",
            },
            {
                "SKU": "SKU-001",
                "Rate": "140.00",
                "Quantity": "5",
                "Discount": "0.0",
                "Invoice Number": "INV-0999",
                "Invoice Date": "2026-06-15",
                "Item Name": "Test Item 1",
            },
        ]

        items = [{"sku": "SKU-001", "qty": 10}, {"sku": "SKU-999", "qty": 1}]
        results = fetch_last_invoiced_prices(
            analytics_client=mock_client,
            workspace_id="WS123",
            customer_id="CUST123",
            items=items,
        )

        self.assertEqual(len(results), 2)

        res1 = results[0]
        self.assertEqual(res1.sku, "SKU-001")
        self.assertTrue(res1.found)
        self.assertEqual(res1.last_billed_price, 150.50)
        self.assertEqual(res1.last_billed_qty, 10.0)
        self.assertEqual(res1.last_invoice_number, "INV-1001")
        self.assertEqual(res1.last_invoice_date, "2026-07-20")

        res2 = results[1]
        self.assertEqual(res2.sku, "SKU-999")
        self.assertFalse(res2.found)
        self.assertIsNone(res2.last_billed_price)

    def test_fetch_last_invoiced_prices_query_failure(self):
        mock_client = MagicMock()
        mock_client.views.query_data.side_effect = RuntimeError("API rate limit exceeded")

        with self.assertRaises(ZohoUsableError):
            fetch_last_invoiced_prices(
                analytics_client=mock_client,
                workspace_id="WS123",
                customer_id="CUST123",
                items=["SKU-001"],
            )

    def test_get_last_billed_prices_for_customer_wrapper(self):
        mock_client = MagicMock()
        mock_client.views.query_data.return_value = [
            {
                "SKU": "SKU-001",
                "Rate": 250.0,
                "Quantity": 2,
                "Invoice Number": "INV-500",
                "Invoice Date": "2026-07-01",
            }
        ]

        res = get_last_billed_prices_for_customer(
            customer_id="CUST-1",
            items=[{"sku": "SKU-001", "qty": 2}],
            workspace_id="WS-TEST",
            analytics_client=mock_client,
        )

        self.assertIsInstance(res, DotDict)
        self.assertEqual(res.customer_id, "CUST-1")
        self.assertEqual(res.workspace_id, "WS-TEST")
        self.assertEqual(res.item_count, 1)
        self.assertEqual(res.found_count, 1)
        self.assertEqual(res.items[0].last_billed_price, 250.0)


if __name__ == "__main__":
    unittest.main()
