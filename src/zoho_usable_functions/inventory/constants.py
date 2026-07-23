"""Constants used by FAN inventory synchronization."""

from pathlib import Path

from ..core.config import Config


DEFAULT_FAN_FILE = Path(Config.FAN_STOCK_FILE)
DEFAULT_OUTPUT_DIR = Path(Config.FAN_OUTPUT_DIR)
FAN_FILENAME_PREFIX = "zoho_inventory_fan_items"
DEFAULT_EXISTING_SNAPSHOT = DEFAULT_OUTPUT_DIR / "zoho_inventory_existing_items_snapshot.csv"
DEFAULT_CREATE_XLSX = DEFAULT_OUTPUT_DIR / f"{FAN_FILENAME_PREFIX}_missing.xlsx"

DEFAULT_FAN_ACCOUNTS = {
    "account_id": Config.FAN_SALES_ACCOUNT_ID,
    "purchase_account_id": Config.FAN_PURCHASE_ACCOUNT_ID,
    "inventory_account_id": Config.FAN_INVENTORY_ACCOUNT_ID,
}

GST_18_TAX_PREFERENCES = [
    {
        "tax_specification": "intra",
        "tax_name": "GST18",
        "tax_percentage": 18,
        "tax_id": Config.ZOHO_GST18_TAX_ID,
    },
    {
        "tax_specification": "inter",
        "tax_name": "IGST18",
        "tax_percentage": 18,
        "tax_id": Config.ZOHO_IGST18_TAX_ID,
    },
]

FAN_STOCK_REPORT_FIELDS = (
    "sku",
    "description",
    "status",
    "category",
    "model_group",
    "product_type",
    "channel",
    "grand_stock",
    "grand_git",
    "total_stock_and_git",
)
