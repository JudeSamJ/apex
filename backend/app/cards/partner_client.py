import time
import random
import uuid
from typing import Dict, Any

class MockIssuingPartnerClient:
    def __init__(self, simulate_latency_ms: int = 100):
        self.simulate_latency_ms = simulate_latency_ms

    def _delay(self):
        if self.simulate_latency_ms > 0:
            time.sleep(self.simulate_latency_ms / 1000.0)

    def create_card(self, entity_id: str, owner_id: str, card_type: str, limit_amount: float) -> Dict[str, Any]:
        self._delay()
        # Generate a fake card token and masked PAN
        card_token = f"tok_mock_{uuid.uuid4().hex[:16]}"
        last_four = str(random.randint(1000, 9999))
        masked_pan = f"**** **** **** {last_four}"
        
        return {
            "card_token": card_token,
            "masked_pan": masked_pan,
            "status": "ACTIVE"
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
