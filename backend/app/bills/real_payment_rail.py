import os
import httpx
from decimal import Decimal
import logging
import uuid

logger = logging.getLogger(__name__)

class RealPaymentRailClient:
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY", "mock_stripe_sandbox_key")
        self.api_url = "https://api.stripe.com/v1/payment_intents"

    def initiate_transfer(self, bank_account_id: str, amount: Decimal) -> str:
        amount_cents = int(amount * 100)
        
        if self.api_key == "mock_stripe_sandbox_key":
            logger.info(f"[Stripe Sandbox Simulator] Initiating transfer of {amount_cents} cents to bank {bank_account_id}")
            return f"pi_stripe_{uuid.uuid4().hex[:12]}"

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "amount": amount_cents,
                "currency": "usd",
                "payment_method_types[]": "us_bank_account",
                "description": f"AP Bill Pay Transfer to bank account {bank_account_id}"
            }
            response = httpx.post(self.api_url, headers=headers, data=data, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"Stripe API payment initiation failed: {response.text}")
                raise Exception(f"Stripe Payment Rail initiation error: {response.text}")
                
            res_data = response.json()
            return res_data["id"]
        except Exception as e:
            logger.exception("Error calling Stripe payment rail")
            raise e
