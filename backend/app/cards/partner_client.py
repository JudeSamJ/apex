import time
import random
import uuid
import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
import stripe


class IssuingPartnerClient(ABC):
    @abstractmethod
    def create_card(
        self, entity_id: str, owner_id: str, card_type: str, limit_amount: float
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def update_limit(self, card_token: str, new_limit: float) -> bool:
        ...

    @abstractmethod
    def freeze_card(self, card_token: str) -> bool:
        ...

    @abstractmethod
    def unfreeze_card(self, card_token: str) -> bool:
        ...

    @abstractmethod
    def get_card_token(self, card_token: str) -> str:
        """Return masked PAN token for display — never a real PAN."""
        ...


class MockIssuingPartnerClient(IssuingPartnerClient):
    def __init__(self, simulate_latency_ms: int = 100):
        self.simulate_latency_ms = simulate_latency_ms
        self._token_to_masked: Dict[str, str] = {}

    def _delay(self):
        if self.simulate_latency_ms > 0:
            time.sleep(self.simulate_latency_ms / 1000.0)

    def create_card(
        self, entity_id: str, owner_id: str, card_type: str, limit_amount: float
    ) -> Dict[str, Any]:
        self._delay()
        card_token = f"tok_mock_{uuid.uuid4().hex[:16]}"
        last_four = str(random.randint(1000, 9999))
        masked_pan = f"**** **** **** {last_four}"
        self._token_to_masked[card_token] = masked_pan

        return {
            "card_token": card_token,
            "masked_pan": masked_pan,
            "status": "ACTIVE",
        }

    def update_limit(self, card_token: str, new_limit: float) -> bool:
        self._delay()
        return True

    def freeze_card(self, card_token: str) -> bool:
        self._delay()
        return True

    def unfreeze_card(self, card_token: str) -> bool:
        self._delay()
        return True

    def get_card_token(self, card_token: str) -> str:
        return self._token_to_masked.get(card_token, "**** **** **** ****")


class StripeIssuingClient(IssuingPartnerClient):
    """Real Stripe Issuing integration using test mode."""
    
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY")
        if not self.api_key:
            raise ValueError("STRIPE_SECRET_KEY environment variable not set")
        
        stripe.api_key = self.api_key
        self.logger = logging.getLogger(__name__)
        
        # Verify we're in test mode
        if not self.api_key.startswith("sk_test_"):
            self.logger.warning("Stripe key does not appear to be a test mode key")
    
    def create_card(
        self, entity_id: str, owner_id: str, card_type: str, limit_amount: float
    ) -> Dict[str, Any]:
        """Create a cardholder and card in Stripe Issuing test mode."""
        try:
            # Create cardholder
            cardholder = stripe.issuing.Cardholder.create(
                name=f"Entity {entity_id} - User {owner_id}",
                email=f"user-{owner_id}@entity-{entity_id}.example.com",
                phone_number="+15555555555",
                status="active",
                type="individual",
                billing={
                    "address": {
                        "line1": "123 Test Street",
                        "city": "San Francisco",
                        "state": "CA",
                        "postal_code": "94105",
                        "country": "US",
                    }
                },
            )
            
            # Create card
            card_params = {
                "cardholder": cardholder.id,
                "currency": "usd",
                "type": "virtual" if card_type.upper() == "VIRTUAL" else "physical",
                "status": "active",
            }
            
            # For physical cards in test mode, we can create them but they won't ship
            if card_type.upper() == "PHYSICAL":
                self.logger.info(f"Creating physical card in test mode (will not ship)")
            
            card = stripe.issuing.Card.create(**card_params)
            
            # Get last4 from card
            last4 = card.get("last4", "0000")
            masked_pan = f"**** **** **** {last4}"
            
            self.logger.info(
                f"Created Stripe card: card_id={card.id}, cardholder_id={cardholder.id}, "
                f"type={card_type}, last4={last4}"
            )
            
            return {
                "card_token": card.id,  # Stripe card ID as our token
                "cardholder_id": cardholder.id,
                "masked_pan": masked_pan,
                "status": "ACTIVE",
                "stripe_card_id": card.id,
            }
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Stripe card creation failed: {e}")
            raise Exception(f"Failed to create card: {str(e)}")
    
    def update_limit(self, card_token: str, new_limit: float) -> bool:
        """Update spending limit via Stripe SpendingControls."""
        try:
            # In Stripe Issuing, limits are set via SpendingControls on the card
            card = stripe.issuing.Card.modify(
                card_token,
                spending_controls={
                    "spending_limits": [
                        {
                            "amount": int(new_limit * 100),  # Convert to cents
                            "currency": "usd",
                            "interval": "per_authorization",
                        }
                    ]
                },
            )
            
            self.logger.info(f"Updated limit for card {card_token} to {new_limit}")
            return True
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Stripe limit update failed: {e}")
            raise Exception(f"Failed to update limit: {str(e)}")
    
    def freeze_card(self, card_token: str) -> bool:
        """Freeze card by setting status to inactive."""
        try:
            card = stripe.issuing.Card.modify(card_token, status="inactive")
            self.logger.info(f"Frozen card {card_token}")
            return True
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Stripe card freeze failed: {e}")
            raise Exception(f"Failed to freeze card: {str(e)}")
    
    def unfreeze_card(self, card_token: str) -> bool:
        """Unfreeze card by setting status to active."""
        try:
            card = stripe.issuing.Card.modify(card_token, status="active")
            self.logger.info(f"Unfrozen card {card_token}")
            return True
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Stripe card unfreeze failed: {e}")
            raise Exception(f"Failed to unfreeze card: {str(e)}")
    
    def get_card_token(self, card_token: str) -> str:
        """Return masked PAN for display."""
        try:
            card = stripe.issuing.Card.retrieve(card_token)
            last4 = card.get("last4", "0000")
            return f"**** **** **** {last4}"
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Stripe card retrieval failed: {e}")
            return "**** **** **** ****"


def get_issuing_client():
    """Factory function to get the appropriate issuing client."""
    use_real = os.getenv("USE_REAL_ISSUING", "False").lower() in ["true", "1"]
    
    if use_real:
        return StripeIssuingClient()
    else:
        return MockIssuingPartnerClient()
