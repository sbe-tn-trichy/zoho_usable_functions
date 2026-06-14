import requests
import json
import logging
from typing import Tuple, Optional, Dict
from zoho.books import ZohoBooksAPI
from zoho.wd import ZohoWorkdriveAPI
from .config import Config

logger = logging.getLogger(__name__)

def fetch_access_tokens(token_url: str = Config.TOKEN_URL) -> Dict[str, Optional[str]]:
    """
    Queries the token service to retrieve active access tokens for Books and Workdrive.
    """
    logger.info(f"Retrieving access tokens from {token_url}...")
    try:
        response = requests.post(token_url)
        response.raise_for_status()
        outer_data = response.json()
        
        books_token = None
        workdrive_token = None
        
        if "body" in outer_data:
            body_data = json.loads(outer_data["body"])
            tokens = body_data.get("tokens", {})
            books_token = tokens.get("books")
            workdrive_token = tokens.get("workdrive")
            
        return {
            "books": books_token,
            "workdrive": workdrive_token
        }
    except Exception as e:
        logger.error(f"Failed to fetch access tokens: {e}")
        return {"books": None, "workdrive": None}

def get_books_client(token: Optional[str] = None, org_id: str = Config.ORG_ID, domain: str = Config.DOMAIN) -> ZohoBooksAPI:
    """
    Instantiates and returns a ZohoBooksAPI client.
    """
    if not token:
        tokens = fetch_access_tokens()
        token = tokens.get("books")
        if not token:
            raise ValueError("No Zoho Books access token available.")
            
    return ZohoBooksAPI(access_token=token, organization_id=org_id, domain=domain)

def get_workdrive_client(token: Optional[str] = None, domain: str = Config.DOMAIN) -> ZohoWorkdriveAPI:
    """
    Instantiates and returns a ZohoWorkdriveAPI client.
    """
    if not token:
        tokens = fetch_access_tokens()
        token = tokens.get("workdrive")
        if not token:
            raise ValueError("No Zoho Workdrive access token available.")
            
    return ZohoWorkdriveAPI(access_token=token, domain=domain)
