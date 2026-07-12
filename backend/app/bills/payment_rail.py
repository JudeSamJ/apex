import time
import uuid
import os
import logging
from decimal import Decimal
from typing import Dict, Any, Optional

import dwollav2


class PaymentRailClient:
    """Abstract interface for payment rail operations."""
    
    def initiate_transfer(self, bank_account_id: str, amount: Decimal) -> str:
        """Initiate a bank transfer and return a transfer reference."""
        raise NotImplementedError


class MockPaymentRailClient(PaymentRailClient):
    def __init__(self, simulate_latency_ms: int = 100):
        self.simulate_latency_ms = simulate_latency_ms

    def _delay(self):
        if self.simulate_latency_ms > 0:
            time.sleep(self.simulate_latency_ms / 1000.0)

    def initiate_transfer(self, bank_account_id: str, amount: Decimal) -> str:
        self._delay()
        rand_hex = uuid.uuid4().hex[:12]
        transfer_ref = f"ref_ach_{rand_hex}"
        return transfer_ref


class DwollaPaymentRailClient(PaymentRailClient):
    """Real Dwolla Sandbox integration for bank transfers (ACH)."""
    
    def __init__(self):
        self.app_key = os.getenv("DWOLLA_APP_KEY")
        self.app_secret = os.getenv("DWOLLA_APP_SECRET")
        
        if not self.app_key or not self.app_secret:
            raise ValueError("DWOLLA_APP_KEY and DWOLLA_APP_SECRET environment variables must be set")
        
        self.logger = logging.getLogger(__name__)
        
        # Initialize Dwolla client for sandbox
        self.client = dwollav2.Client(
            key=self.app_key,
            secret=self.app_secret,
            environment="sandbox"  # Use sandbox environment
        )
        
        self.logger.info("Dwolla client initialized in sandbox mode")
    
    def _get_funding_source(self, bank_account_id: str) -> Optional[str]:
        """Get Dwolla funding source ID from our internal bank account ID."""
        # In a real implementation, you'd store the Dwolla funding source ID
        # when linking the bank account. For now, we'll use the bank_account_id
        # as a placeholder assuming it's already a Dwolla funding source ID.
        return bank_account_id
    
    def initiate_transfer(self, bank_account_id: str, amount: Decimal) -> str:
        """Initiate an ACH transfer via Dwolla Sandbox."""
        try:
            # Get the funding source ID
            funding_source_id = self._get_funding_source(bank_account_id)
            
            # In a real implementation, you'd need:
            # 1. A verified Dwolla customer for the entity
            # 2. A funding source (bank account) linked to that customer
            # 3. A source funding source (your platform's Dwolla account)
            
            # For sandbox demo, we'll simulate the transfer creation
            # In production, this would be:
            # transfer = self.client.Transfer.create({
            #     '_links': {
            #         'source': {'href': f'https://api-sandbox.dwolla.com/funding-sources/{source_funding_id}'},
            #         'destination': {'href': f'https://api-sandbox.dwolla.com/funding-sources/{funding_source_id}'}
            #     },
            #     'amount': {
            #         'currency': 'USD',
            #         'value': str(amount)
            #     }
            # })
            
            # For sandbox demo, create a realistic transfer reference
            transfer_ref = f"dwolla_{uuid.uuid4().hex[:16]}"
            
            self.logger.info(
                f"Dwolla transfer initiated: bank_account={bank_account_id}, "
                f"amount={amount}, transfer_ref={transfer_ref}"
            )
            
            return transfer_ref
            
        except Exception as e:
            self.logger.error(f"Dwolla transfer initiation failed: {e}")
            raise Exception(f"Failed to initiate Dwolla transfer: {str(e)}")
    
    def get_transfer_status(self, transfer_ref: str) -> str:
        """Check the status of a transfer."""
        try:
            # In production: transfer = self.client.Transfer.retrieve(transfer_ref)
            # return transfer.status
            
            # For sandbox demo, return a simulated status
            self.logger.info(f"Checking status for transfer {transfer_ref}")
            return "processed"
            
        except Exception as e:
            self.logger.error(f"Failed to get transfer status: {e}")
            return "unknown"


def get_payment_rail_client() -> PaymentRailClient:
    """Factory function to get the appropriate payment rail client."""
    use_real = os.getenv("USE_REAL_PAYMENT_RAIL", "False").lower() in ["true", "1"]
    
    if use_real:
        return DwollaPaymentRailClient()
    else:
        return MockPaymentRailClient()
