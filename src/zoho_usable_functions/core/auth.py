import requests
import json
import logging
from typing import Tuple, Optional, Dict
from zoho.books import ZohoBooksAPI
from zoho.wd import ZohoWorkdriveAPI
from zoho.inventory import ZohoInventoryAPI
from zoho.creator import ZohoCreatorAPI
from zoho.base_client import BaseZohoClient
from .config import Config
from .exceptions import ZohoAuthError

logger = logging.getLogger(__name__)


class ZohoCreatorAPIWithoutEnvironment(ZohoCreatorAPI):
    """Creator client variant for APIs that reject the environment header."""

    def request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ):
        return BaseZohoClient.request(
            self,
            method=method,
            endpoint=endpoint,
            json=json,
            params=params,
            headers=headers,
        )

def fetch_access_tokens(token_url: str = Config.TOKEN_URL) -> Dict[str, Optional[str]]:
    """
    Queries the token service to retrieve active access tokens for Zoho services.
    """
    logger.info(f"Retrieving access tokens from {token_url}...")
    try:
        response = requests.post(token_url)
        response.raise_for_status()
        outer_data = response.json()
        
        books_token = None
        workdrive_token = None
        inventory_token = None
        creator_token = None
        analytics_token = None
        
        body_data = outer_data.get("body", outer_data)
        if isinstance(body_data, str):
            body_data = json.loads(body_data)
        tokens = body_data.get("tokens", {}) if isinstance(body_data, dict) else {}
        books_token = tokens.get("books")
        workdrive_token = tokens.get("workdrive")
        inventory_token = tokens.get("inventory")
        creator_token = tokens.get("creator")
        analytics_token = tokens.get("analytics")
            
        return {
            "books": books_token,
            "workdrive": workdrive_token,
            "inventory": inventory_token,
            "creator": creator_token,
            "analytics": analytics_token,
        }
    except Exception as e:
        logger.error(f"Failed to fetch access tokens: {e}")
        return {"books": None, "workdrive": None, "inventory": None, "creator": None, "analytics": None}

def get_books_client(token: Optional[str] = None, org_id: str = Config.ORG_ID, domain: str = Config.DOMAIN) -> ZohoBooksAPI:
    """
    Instantiates and returns a ZohoBooksAPI client.
    """
    if not token:
        tokens = fetch_access_tokens()
        token = tokens.get("books")
        if not token:
            raise ZohoAuthError("No Zoho Books access token available.")
            
    return ZohoBooksAPI(access_token=token, organization_id=org_id, domain=domain)

def get_workdrive_client(token: Optional[str] = None, domain: str = Config.DOMAIN) -> ZohoWorkdriveAPI:
    """
    Instantiates and returns a ZohoWorkdriveAPI client.
    """
    if not token:
        tokens = fetch_access_tokens()
        token = tokens.get("workdrive")
        if not token:
            raise ZohoAuthError("No Zoho Workdrive access token available.")
            
    return ZohoWorkdriveAPI(access_token=token, domain=domain)

def get_inventory_client(
    token: Optional[str] = None,
    org_id: str = Config.ORG_ID,
    domain: str = Config.DOMAIN,
    allow_books_token: bool = False,
) -> ZohoInventoryAPI:
    """
    Instantiates and returns a ZohoInventoryAPI client.
    """
    if not token:
        tokens = fetch_access_tokens()
        token = tokens.get("inventory")
        if not token and allow_books_token:
            token = tokens.get("books")
        if not token:
            raise ZohoAuthError("No Zoho Inventory access token available.")

    return ZohoInventoryAPI(access_token=token, organization_id=org_id, domain=domain)

def get_creator_client(
    token: Optional[str] = None,
    account_owner_name: str = Config.CREATOR_ACCOUNT_OWNER_NAME,
    domain: str = Config.DOMAIN,
    environment: str = Config.CREATOR_ENVIRONMENT,
) -> ZohoCreatorAPI:
    """
    Instantiates and returns a ZohoCreatorAPI client.
    """
    if not account_owner_name:
        raise ZohoAuthError("No Zoho Creator account owner name configured.")
    if not token:
        tokens = fetch_access_tokens()
        token = tokens.get("creator")
        if not token:
            raise ZohoAuthError("No Zoho Creator access token available.")

    return ZohoCreatorAPIWithoutEnvironment(
        access_token=token,
        account_owner_name=account_owner_name,
        domain=domain,
        environment=environment,
    )

def get_analytics_token(token: Optional[str] = None) -> str:
    """
    Returns a Zoho Analytics access token from the token service.
    """
    if token:
        return token
    tokens = fetch_access_tokens()
    analytics_token = tokens.get("analytics")
    if not analytics_token:
        raise ZohoAuthError("No Zoho Analytics access token available.")
    return analytics_token
