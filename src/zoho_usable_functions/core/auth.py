import logging
from typing import Optional, Dict
from zoho import HttpTokenProvider, ZohoAnalyticsAPI
from zoho.books import ZohoBooksAPI
from zoho.wd import ZohoWorkdriveAPI
from zoho.inventory import ZohoInventoryAPI
from zoho.creator import ZohoCreatorAPI
from .config import Config
from .exceptions import ZohoAuthError

logger = logging.getLogger(__name__)


def fetch_access_tokens(token_url: str = Config.TOKEN_URL) -> Dict[str, Optional[str]]:
    """
    Queries the token service to retrieve active access tokens for Zoho services.
    """
    logger.info("Retrieving access tokens from configured token service.")
    try:
        tokens = HttpTokenProvider(token_url).get_tokens()
        return {service: tokens.get(service) for service in ("books", "workdrive", "inventory", "creator", "analytics")}
    except Exception as e:
        logger.error("Failed to fetch access tokens: %s", e)
        raise ZohoAuthError("Failed to fetch access tokens from the configured token service.") from e

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

    return ZohoCreatorAPI(
        access_token=token,
        account_owner_name=account_owner_name,
        domain=domain,
        environment=environment,
        send_environment_header=False,
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


def get_analytics_client(
    token: Optional[str] = None,
    org_id: str = Config.PAYMENT_ANALYTICS_ORG_ID,
    domain: str = Config.DOMAIN,
) -> ZohoAnalyticsAPI:
    """Instantiate a Zoho Analytics SDK client for payment workflows."""
    return ZohoAnalyticsAPI(
        access_token=token or get_analytics_token(),
        organization_id=org_id,
        domain=domain,
    )
