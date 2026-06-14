import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the root directory of the project
# We check if .env exists in the current directory, parent, or project root
root_dir = Path(__file__).resolve().parent.parent.parent.parent
env_path = root_dir / '.env'

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

class Config:
    # API Access
    TOKEN_URL = os.getenv("TOKEN_URL", "http://localhost:3000/server/new/tokens")
    ORG_ID = os.getenv("ORG_ID", "60018185359")
    DOMAIN = os.getenv("DOMAIN", "in")

    # Zoho WorkDrive Configurations
    POLYCAB_FOLDER_ID = os.getenv("POLYCAB_FOLDER_ID", "wue3rf80474a32d3f4b67af8652d97ea5ab6c")

    # Local Directory Paths
    PROJECT_ROOT = str(root_dir)
    FILES_DIR = os.getenv("FILES_DIR", str(root_dir / "files" / "polycab" / "cn"))
    POLYCAB_LEDGER_PATH = os.getenv(
        "POLYCAB_LEDGER_PATH", 
        str(root_dir / "files" / "polycab" / "ledger" / "277498_ReconciliationLedger_1-Jan-26_to_31-Mar-26.xls")
    )

    # Zoho Books Entity IDs
    POLYCAB_VENDOR_ID = os.getenv("POLYCAB_VENDOR_ID", "1094368000000175001")
    ZOHO_RSO_CN_ITEM_ID = os.getenv("ZOHO_RSO_CN_ITEM_ID", "1094368000028456138")
    ZOHO_SCHEME_CN_ITEM_ID = os.getenv("ZOHO_SCHEME_CN_ITEM_ID", "1094368000000311103")
    ZOHO_GST0_TAX_ID = os.getenv("ZOHO_GST0_TAX_ID", "1094368000000014279")
