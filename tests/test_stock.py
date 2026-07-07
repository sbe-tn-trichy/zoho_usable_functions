import unittest
from unittest.mock import MagicMock, patch
from zoho_usable_functions.reconciliation.stock import find_negative_stock_items

class TestStock(unittest.TestCase):
    def setUp(self):
        self.books_client = MagicMock()
        
    def test_find_negative_stock_items_success(self):
        # 1. Mock list_all response
        self.books_client.items.list_all.return_value = [
            {"item_id": "item_1", "sku": "SKU-1", "name": "Item 1"},
            {"item_id": "item_2", "sku": "SKU-2", "name": "Item 2"},
            {"item_id": "item_3", "sku": "SKU-3", "name": "Item 3"}
        ]
        
        # 2. Mock request itemdetails response
        self.books_client.request.return_value = {
            "items": [
                {
                    "item_id": "item_1",
                    "name": "Item 1",
                    "sku": "SKU-1",
                    "stock_on_hand": 10.0,
                    "status": "active",
                    "custom_fields": [{"api_name": "cf_deprecated", "value": False}],
                    "locations": [
                        {
                            "location_name": "SBE",
                            "location_stock_on_hand": -5.0
                        },
                        {
                            "location_name": "ZEISS",
                            "location_stock_on_hand": 15.0
                        }
                    ]
                },
                {
                    "item_id": "item_2",
                    "name": "Item 2",
                    "sku": "SKU-2",
                    "stock_on_hand": 0.0,
                    "status": "active",
                    "custom_fields": [{"api_name": "cf_deprecated", "value": "true"}],
                    "locations": [
                        {
                            "location_name": "SBE",
                            "location_stock_on_hand": 0.0
                        }
                    ]
                },
                {
                    "item_id": "item_3",
                    "name": "Item 3",
                    "sku": "SKU-3",
                    "stock_on_hand": -2.0,
                    "status": "inactive",
                    "custom_fields": [],
                    "locations": [
                        {
                            "location_name": "sbe",  # case-insensitive check
                            "location_stock_on_hand": "-2.5"  # string value check
                        }
                    ]
                }
            ]
        }
        
        results = find_negative_stock_items(self.books_client, "SBE")
        
        self.assertEqual(len(results), 2)
        
        # Verify first item
        self.assertEqual(results[0]["item_id"], "item_1")
        self.assertEqual(results[0]["sku"], "SKU-1")
        self.assertEqual(results[0]["location_stock_on_hand"], -5.0)
        self.assertFalse(results[0]["is_deprecated"])
        
        # Verify second item (case-insensitive and string conversion check)
        self.assertEqual(results[1]["item_id"], "item_3")
        self.assertEqual(results[1]["sku"], "SKU-3")
        self.assertEqual(results[1]["location_stock_on_hand"], -2.5)
        self.assertFalse(results[1]["is_deprecated"])

        # Check call patterns
        self.books_client.items.list_all.assert_called_once()
        self.books_client.request.assert_called_once_with(
            "GET", "itemdetails", params={"item_ids": "item_1,item_2,item_3"}
        )

    def test_find_negative_stock_items_with_purchase_account(self):
        self.books_client.items.list_by_purchase_account.return_value = [
            {"item_id": "item_abc", "sku": "SKU-ABC", "name": "Item ABC"}
        ]
        self.books_client.request.return_value = {
            "items": [
                {
                    "item_id": "item_abc",
                    "name": "Item ABC",
                    "sku": "SKU-ABC",
                    "stock_on_hand": 1.0,
                    "status": "active",
                    "locations": [
                        {
                            "location_name": "SBE",
                            "location_stock_on_hand": -1.0
                        }
                    ]
                }
            ]
        }
        
        results = find_negative_stock_items(self.books_client, "SBE", purchase_account_id="1094368000051535654")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["item_id"], "item_abc")
        self.assertEqual(results[0]["location_stock_on_hand"], -1.0)
        
        self.books_client.items.list_by_purchase_account.assert_called_once_with("1094368000051535654")
        self.books_client.items.list_all.assert_not_called()

    def test_find_negative_stock_items_no_ids(self):
        self.books_client.items.list_all.return_value = []
        
        results = find_negative_stock_items(self.books_client, "SBE")
        self.assertEqual(results, [])
        self.books_client.request.assert_not_called()

    def test_find_negative_stock_items_api_error_on_details(self):
        self.books_client.items.list_all.return_value = [
            {"item_id": "item_1"}
        ]
        self.books_client.request.side_effect = Exception("API rate limit exceeded")
        
        results = find_negative_stock_items(self.books_client, "SBE")
        self.assertEqual(results, [])  # Should continue gracefully and return empty list

if __name__ == "__main__":
    unittest.main()
