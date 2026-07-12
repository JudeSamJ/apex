import os
import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime


class QuickBooksOnlineClient:
    """Real QuickBooks Online Sandbox integration for accounting/ERP sync."""
    
    def __init__(self):
        self.client_id = os.getenv("QBO_CLIENT_ID")
        self.client_secret = os.getenv("QBO_CLIENT_SECRET")
        self.redirect_uri = os.getenv("QBO_REDIRECT_URI", "http://localhost:5173/qbo-callback")
        
        if not self.client_id or not self.client_secret:
            raise ValueError("QBO_CLIENT_ID and QBO_CLIENT_SECRET environment variables must be set")
        
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://sandbox-quickbooks.api.intuit.com/v3"
        self.oauth_url = "https://oauth.platform.intuit.com/v2/oauth2/tokens/bearer"
        
        self.logger.info("QuickBooks Online client initialized in sandbox mode")
    
    def get_oauth_url(self, state: str) -> str:
        """Generate OAuth authorization URL for QBO connection."""
        scopes = "com.intuit.quickbooks.accounting"
        
        url = (
            f"https://app.sandbox.qbo.intuit.com/app/oauth/connectv2?"
            f"response_type=code&"
            f"client_id={self.client_id}&"
            f"scope={scopes}&"
            f"redirect_uri={self.redirect_uri}&"
            f"state={state}"
        )
        
        self.logger.info(f"Generated QBO OAuth URL with state: {state}")
        return url
    
    def exchange_code_for_token(self, code: str, realm_id: str) -> Dict[str, Any]:
        """Exchange OAuth authorization code for access token."""
        try:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri
            }
            
            auth = (self.client_id, self.client_secret)
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            response = httpx.post(
                self.oauth_url,
                data=data,
                auth=auth,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            
            token_data = response.json()
            
            self.logger.info(f"Exchanged OAuth code for token, realm_id={realm_id}")
            
            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "realm_id": realm_id,
                "expires_in": token_data.get("expires_in", 3600)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to exchange OAuth code: {e}")
            raise Exception(f"Failed to exchange OAuth code: {str(e)}")
    
    def get_chart_of_accounts(self, access_token: str, realm_id: str) -> List[Dict[str, Any]]:
        """Retrieve chart of accounts from QBO sandbox company."""
        try:
            url = f"{self.base_url}/company/{realm_id}/query?query=SELECT%20*%20FROM%20Account"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            response = httpx.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            data = response.json()
            accounts = data.get("QueryResponse", {}).get("Account", [])
            
            self.logger.info(f"Retrieved {len(accounts)} accounts from QBO realm {realm_id}")
            
            return accounts
            
        except Exception as e:
            self.logger.error(f"Failed to get chart of accounts: {e}")
            raise Exception(f"Failed to get chart of accounts: {str(e)}")
    
    def create_journal_entry(
        self,
        access_token: str,
        realm_id: str,
        line_items: List[Dict[str, Any]],
        tx_date: str
    ) -> Dict[str, Any]:
        """Create a journal entry in QBO for transaction sync."""
        try:
            url = f"{self.base_url}/company/{realm_id}/journalentry"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            payload = {
                "Line": line_items,
                "TxnDate": tx_date
            }
            
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            data = response.json()
            journal_entry = data.get("JournalEntry", {})
            
            self.logger.info(f"Created journal entry {journal_entry.get('Id')} in QBO realm {realm_id}")
            
            return journal_entry
            
        except Exception as e:
            self.logger.error(f"Failed to create journal entry: {e}")
            raise Exception(f"Failed to create journal entry: {str(e)}")
    
    def create_bill(
        self,
        access_token: str,
        realm_id: str,
        vendor_name: str,
        line_items: List[Dict[str, Any]],
        due_date: str
    ) -> Dict[str, Any]:
        """Create a bill in QBO for bill sync."""
        try:
            url = f"{self.base_url}/company/{realm_id}/bill"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            payload = {
                "VendorRef": {"name": vendor_name},
                "Line": line_items,
                "DueDate": due_date
            }
            
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            data = response.json()
            bill = data.get("Bill", {})
            
            self.logger.info(f"Created bill {bill.get('Id')} in QBO realm {realm_id}")
            
            return bill
            
        except Exception as e:
            self.logger.error(f"Failed to create bill: {e}")
            raise Exception(f"Failed to create bill: {str(e)}")


class MockQBOClient:
    """Mock QBO client for testing without real integration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Using MockQBOClient")
    
    def get_oauth_url(self, state: str) -> str:
        """Return fake OAuth URL."""
        return f"https://mock-qbo.example.com/oauth?state={state}"
    
    def exchange_code_for_token(self, code: str, realm_id: str) -> Dict[str, Any]:
        """Return fake token data."""
        return {
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "realm_id": realm_id,
            "expires_in": 3600
        }
    
    def get_chart_of_accounts(self, access_token: str, realm_id: str) -> List[Dict[str, Any]]:
        """Return fake chart of accounts."""
        return [
            {"Id": "1", "Name": "Cash", "AccountType": "Asset"},
            {"Id": "2", "Name": "Accounts Receivable", "AccountType": "Asset"},
            {"Id": "3", "Name": "Accounts Payable", "AccountType": "Liability"},
            {"Id": "4", "Name": "Operating Expenses", "AccountType": "Expense"},
        ]
    
    def create_journal_entry(
        self,
        access_token: str,
        realm_id: str,
        line_items: List[Dict[str, Any]],
        tx_date: str
    ) -> Dict[str, Any]:
        """Return fake journal entry."""
        return {"Id": "mock_je_123", "TxnDate": tx_date}
    
    def create_bill(
        self,
        access_token: str,
        realm_id: str,
        vendor_name: str,
        line_items: List[Dict[str, Any]],
        due_date: str
    ) -> Dict[str, Any]:
        """Return fake bill."""
        return {"Id": "mock_bill_456", "VendorRef": {"name": vendor_name}}


def get_qbo_client():
    """Factory function to get the appropriate QBO client."""
    use_real = os.getenv("USE_REAL_QBO", "False").lower() in ["true", "1"]
    
    if use_real:
        return QuickBooksOnlineClient()
    else:
        return MockQBOClient()
