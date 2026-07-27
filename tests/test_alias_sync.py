import os
import unittest
from unittest.mock import MagicMock

from zoho_usable_functions.inventory.alias_sync import (
    group_alias_mappings,
    sync_item_aliases,
)


class TestAliasSync(unittest.TestCase):
    def test_group_alias_mappings(self):
        sample_mappings = [
            {"zoho_sku": "SKU-1", "json_name": "NEOSEAL A", "zoho_name": "Zoho A"},
            {"zoho_sku": "SKU-1", "json_name": "NEOSEAL A VAR", "zoho_name": "Zoho A"},
            {"zoho_sku": "SKU-2", "json_name": "NEOSEAL B", "zoho_name": "Zoho B"},
        ]
        grouped = group_alias_mappings(sample_mappings)
        self.assertIn("sku-1", grouped)
        self.assertEqual(len(grouped["sku-1"]["aliases"]), 2)
        self.assertIn("NEOSEAL A", grouped["sku-1"]["aliases"])
        self.assertIn("NEOSEAL A VAR", grouped["sku-1"]["aliases"])

    def test_sync_item_aliases_dry_run(self):
        mock_client = MagicMock()
        
        # Mock search response
        mock_client.request.side_effect = lambda method, endpoint, params=None, json=None: {
            "items": [{"item_id": "item_123", "sku": "SKU-1", "name": "Zoho Item 1"}]
        } if method == "GET" and endpoint == "items" else {"code": 0}

        # Mock detail item response
        mock_client.items.get.return_value = {
            "item": {
                "item_id": "item_123",
                "name": "Zoho Item 1",
                "sku": "SKU-1",
                "alias_name": "",
            }
        }

        mappings = [
            {"zoho_sku": "SKU-1", "json_name": "GEMINI NAME 1", "zoho_name": "Zoho Item 1"}
        ]

        summary = sync_item_aliases(mock_client, mappings, execute=False)
        self.assertEqual(summary["total_mapped_skus"], 1)
        self.assertEqual(summary["found_in_zoho"], 1)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["details"][0]["status"], "dry_run_update")
        self.assertEqual(summary["details"][0]["new_alias"], "GEMINI NAME 1")

    def test_sync_item_aliases_execute(self):
        mock_client = MagicMock()
        
        mock_client.request.side_effect = lambda method, endpoint, params=None, json=None: (
            {"items": [{"item_id": "item_123", "sku": "SKU-1", "name": "Zoho Item 1"}]}
            if method == "GET"
            else {"code": 0, "item": {"alias_name": "GEMINI NAME 1"}}
        )

        mock_client.items.get.return_value = {
            "item": {
                "item_id": "item_123",
                "name": "Zoho Item 1",
                "sku": "SKU-1",
                "alias_name": "",
            }
        }

        mappings = [
            {"zoho_sku": "SKU-1", "json_name": "GEMINI NAME 1", "zoho_name": "Zoho Item 1"}
        ]

        summary = sync_item_aliases(mock_client, mappings, execute=True)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["details"][0]["status"], "updated")
        
        # Verify PUT request payload
        mock_client.request.assert_called_with(
            "PUT",
            "items/item_123",
            json={"name": "Zoho Item 1", "alias_name": "GEMINI NAME 1"}
        )


if __name__ == "__main__":
    unittest.main()
