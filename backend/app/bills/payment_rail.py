import time
import uuid
import os
from decimal import Decimal

class MockPaymentRailClient:
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

def get_payment_rail_client():
    # If environment variable states to use real rail, swap to Stripe sandbox client
    if os.getenv("USE_REAL_PAYMENT_RAIL", "False").lower() in ["true", "1"]:
        from app.bills.real_payment_rail import RealPaymentRailClient
        return RealPaymentRailClient()
    return MockPaymentRailClient()
