import os
import logging
from abc import ABC, abstractmethod
from decimal import Decimal

import httpx

from app.secrets.provider import get_secret

logger = logging.getLogger(__name__)

# Currencies this platform recognizes. Kept intentionally small — every
# currency here must have a rate in MockFXRateClient's table, and every
# amount field that stores a currency code validates against this set.
SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR"}


class FXRateClient(ABC):
    @abstractmethod
    def get_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """Units of to_currency per 1 unit of from_currency."""
        ...


class ExchangeRateAPIClient(FXRateClient):
    """Real FX rates via exchangerate-api.com's v6 API."""

    def __init__(self):
        self.api_key = get_secret("EXCHANGE_RATE_API_KEY")
        if not self.api_key:
            raise ValueError("EXCHANGE_RATE_API_KEY environment variable must be set")
        self.base_url = "https://v6.exchangerate-api.com/v6"
        self.logger = logging.getLogger(__name__)

    def get_rate(self, from_currency: str, to_currency: str) -> Decimal:
        try:
            response = httpx.get(
                f"{self.base_url}/{self.api_key}/pair/{from_currency}/{to_currency}", timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return Decimal(str(data["conversion_rate"]))
        except Exception as e:
            self.logger.error(f"Failed to fetch FX rate {from_currency}->{to_currency}: {e}")
            raise Exception(f"Failed to fetch FX rate: {str(e)}")


class MockFXRateClient(FXRateClient):
    """Deterministic, fixed rates for sandbox/demo/testing — pivoted through
    USD so any pair in SUPPORTED_CURRENCIES resolves without a real API."""

    _USD_RATES = {
        "USD": Decimal("1.00"),
        "EUR": Decimal("0.92"),
        "GBP": Decimal("0.79"),
        "CAD": Decimal("1.36"),
        "AUD": Decimal("1.52"),
        "JPY": Decimal("149.50"),
        "INR": Decimal("83.30"),
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_rate(self, from_currency: str, to_currency: str) -> Decimal:
        if from_currency == to_currency:
            return Decimal("1")
        if from_currency not in self._USD_RATES or to_currency not in self._USD_RATES:
            raise ValueError(f"Unsupported currency pair: {from_currency} -> {to_currency}")
        return self._USD_RATES[to_currency] / self._USD_RATES[from_currency]


def get_fx_client() -> FXRateClient:
    """Factory function to get the appropriate FX rate client."""
    use_real = os.getenv("USE_REAL_FX", "False").lower() in ["true", "1"]

    if use_real:
        return ExchangeRateAPIClient()
    else:
        return MockFXRateClient()
