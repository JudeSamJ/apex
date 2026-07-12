import os
import logging
from typing import Dict, Any, Optional

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest


class PlaidClient:
    """Real Plaid Sandbox integration for bank account linking."""
    
    def __init__(self):
        self.client_id = os.getenv("PLAID_CLIENT_ID")
        self.secret = os.getenv("PLAID_SECRET")
        
        if not self.client_id or not self.secret:
            raise ValueError("PLAID_CLIENT_ID and PLAID_SECRET environment variables must be set")
        
        self.logger = logging.getLogger(__name__)
        
        # Initialize Plaid client for sandbox (version 8.12.0 compatible)
        configuration = plaid.Configuration()
        configuration.host = plaid.Environment.Sandbox
        configuration.api_key = {}
        configuration.api_key['clientId'] = self.client_id
        configuration.api_key['secret'] = self.secret
        self.api_client = plaid_api.PlaidApi(configuration)
        
        self.logger.info("Plaid client initialized in sandbox mode")
    
    def create_link_token(
        self,
        entity_id: str,
        user_id: str,
        redirect_uri: Optional[str] = None
    ) -> str:
        """Create a Plaid Link token for the frontend to initialize Plaid Link."""
        try:
            # Create a link token for the frontend
            request = LinkTokenCreateRequest(
                user=LinkTokenCreateRequestUser(
                    client_user_id=f"{entity_id}_{user_id}"
                ),
                client_name="Ramp Clone B2B Platform",
                products=[Products("auth")],
                country_codes=[CountryCode("US")],
                language="en",
                redirect_uri=redirect_uri if redirect_uri else "http://localhost:5173/plaid-callback"
            )
            
            response = self.api_client.link_token_create(request)
            link_token = response['link_token']
            
            self.logger.info(f"Created Plaid link token for entity {entity_id}, user {user_id}")
            return link_token
            
        except Exception as e:
            self.logger.error(f"Failed to create Plaid link token: {e}")
            raise Exception(f"Failed to create Plaid link token: {str(e)}")
    
    def exchange_public_token(self, public_token: str) -> Dict[str, Any]:
        """Exchange a public token from Plaid Link for an access token and item ID."""
        try:
            request = ItemPublicTokenExchangeRequest(
                public_token=public_token
            )
            
            response = self.api_client.item_public_token_exchange(request)
            access_token = response['access_token']
            item_id = response['item_id']
            
            self.logger.info(f"Exchanged public token for access_token, item_id={item_id}")
            
            return {
                "access_token": access_token,
                "item_id": item_id
            }
            
        except Exception as e:
            self.logger.error(f"Failed to exchange public token: {e}")
            raise Exception(f"Failed to exchange public token: {str(e)}")
    
    def get_accounts(self, access_token: str) -> list:
        """Get account information for a linked item."""
        try:
            request = AccountsGetRequest(access_token=access_token)
            response = self.api_client.accounts_get(request)
            
            accounts = response['accounts']
            self.logger.info(f"Retrieved {len(accounts)} accounts for access_token")
            
            return accounts
            
        except Exception as e:
            self.logger.error(f"Failed to get accounts: {e}")
            raise Exception(f"Failed to get accounts: {str(e)}")
    
    def get_account_mask(self, access_token: str, account_id: str) -> str:
        """Get the masked account number (last 4 digits) for a specific account."""
        try:
            accounts = self.get_accounts(access_token)
            
            for account in accounts:
                if account['account_id'] == account_id:
                    mask = account.get('mask', '')
                    self.logger.info(f"Retrieved mask {mask} for account {account_id}")
                    return mask
            
            raise ValueError(f"Account {account_id} not found")
            
        except Exception as e:
            self.logger.error(f"Failed to get account mask: {e}")
            raise Exception(f"Failed to get account mask: {str(e)}")


class MockPlaidClient:
    """Mock Plaid client for testing without real Plaid integration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Using MockPlaidClient")
    
    def create_link_token(
        self,
        entity_id: str,
        user_id: str,
        redirect_uri: Optional[str] = None
    ) -> str:
        """Return a fake link token."""
        import uuid
        fake_token = f"link-sandbox-{uuid.uuid4().hex}"
        self.logger.info(f"Mock: Created link token {fake_token}")
        return fake_token
    
    def exchange_public_token(self, public_token: str) -> Dict[str, Any]:
        """Return fake access token and item ID."""
        import uuid
        return {
            "access_token": f"access-sandbox-{uuid.uuid4().hex}",
            "item_id": f"item-{uuid.uuid4().hex}"
        }
    
    def get_accounts(self, access_token: str) -> list:
        """Return fake account list."""
        return [
            {
                'account_id': 'account_1',
                'name': 'Plaid Checking',
                'type': 'depository',
                'subtype': 'checking',
                'mask': '1234'
            }
        ]
    
    def get_account_mask(self, access_token: str, account_id: str) -> str:
        """Return fake mask."""
        return "1234"


def get_plaid_client():
    """Factory function to get the appropriate Plaid client."""
    use_real = os.getenv("USE_REAL_PLAID", "False").lower() in ["true", "1"]
    
    if use_real:
        return PlaidClient()
    else:
        return MockPlaidClient()
