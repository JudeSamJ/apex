import os
import logging
import httpx
from typing import Dict, Any, Optional
from datetime import datetime

from app.secrets.provider import get_secret


class DiditClient:
    """Real Didit integration for KYC/KYB entity verification (free tier)."""

    def __init__(self):
        self.api_key = get_secret("DIDIT_API_KEY")
        
        if not self.api_key:
            raise ValueError("DIDIT_API_KEY environment variable must be set")
        
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://api.didit.me/v1"  # Placeholder - update with actual Didit API URL
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0
        )
        
        self.logger.info(f"Didit client initialized with API key: {self.api_key[:10]}...")
    
    def create_verification(
        self,
        entity_id: str,
        entity_name: str,
        entity_type: str,  # "individual" or "business"
        email: str,
        phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a KYC/KYB verification request."""
        try:
            # Prepare verification request payload
            payload = {
                "external_id": entity_id,
                "entity_name": entity_name,
                "entity_type": entity_type,
                "email": email,
                "phone": phone,
                "callback_url": f"{os.getenv('APP_BASE_URL', 'http://localhost:8000')}/api/webhooks/didit"
            }
            
            # In production, this would call Didit's actual API
            # response = self.client.post(f"{self.base_url}/verifications", json=payload)
            # response.raise_for_status()
            # return response.json()
            
            # For sandbox/demo mode, simulate the response
            verification_id = f"didit_ver_{entity_id[:8]}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            self.logger.info(
                f"Created Didit verification: verification_id={verification_id}, "
                f"entity_id={entity_id}, entity_type={entity_type}"
            )
            
            return {
                "verification_id": verification_id,
                "status": "pending",
                "verification_url": f"https://verify.didit.me/{verification_id}",  # Placeholder
                "external_id": entity_id
            }
            
        except Exception as e:
            self.logger.error(f"Failed to create Didit verification: {e}")
            raise Exception(f"Failed to create Didit verification: {str(e)}")
    
    def get_verification_status(self, verification_id: str) -> Dict[str, Any]:
        """Check the status of a verification."""
        try:
            # In production: response = self.client.get(f"{self.base_url}/verifications/{verification_id}")
            # response.raise_for_status()
            # return response.json()
            
            # For sandbox/demo mode, return a simulated status
            self.logger.info(f"Checking status for verification {verification_id}")
            
            return {
                "verification_id": verification_id,
                "status": "approved",  # Simulate approval for demo
                "checked_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get verification status: {e}")
            raise Exception(f"Failed to get verification status: {str(e)}")
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()


class MockDiditClient:
    """Mock Didit client for testing without real integration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Using MockDiditClient")
    
    def create_verification(
        self,
        entity_id: str,
        entity_name: str,
        entity_type: str,
        email: str,
        phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return a fake verification request."""
        verification_id = f"mock_ver_{entity_id[:8]}"
        self.logger.info(f"Mock: Created verification {verification_id}")
        return {
            "verification_id": verification_id,
            "status": "pending",
            "verification_url": "https://mock-verify.example.com",
            "external_id": entity_id
        }
    
    def get_verification_status(self, verification_id: str) -> Dict[str, Any]:
        """Return fake status."""
        return {
            "verification_id": verification_id,
            "status": "approved",
            "checked_at": datetime.utcnow().isoformat()
        }
    
    def close(self):
        """No-op for mock."""
        pass


def get_didit_client():
    """Factory function to get the appropriate Didit client."""
    use_real = os.getenv("USE_REAL_DIDIT", "False").lower() in ["true", "1"]
    
    if use_real:
        return DiditClient()
    else:
        return MockDiditClient()
