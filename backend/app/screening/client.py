import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List

import httpx

from app.secrets.provider import get_secret

logger = logging.getLogger(__name__)


class SanctionsScreeningClient(ABC):
    @abstractmethod
    def screen(self, subject_name: str) -> Dict[str, Any]:
        """Screen a name against sanctions/watchlists. Returns
        {"status": "CLEAR" | "HIT", "provider": str, "matches": [...]}"""
        ...


class ComplyAdvantageClient(SanctionsScreeningClient):
    """Real ComplyAdvantage Search API integration for OFAC/sanctions/PEP screening."""

    def __init__(self):
        self.api_key = get_secret("COMPLYADVANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError("COMPLYADVANTAGE_API_KEY environment variable must be set")

        self.base_url = "https://api.complyadvantage.com"
        self.logger = logging.getLogger(__name__)

    def screen(self, subject_name: str) -> Dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/searches",
                headers={"Authorization": f"Token {self.api_key}"},
                json={
                    "search_term": subject_name,
                    "fuzziness": 0.6,
                    "filters": {"types": ["sanction", "warning", "fitness-probity"]},
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            hits: List[Dict[str, Any]] = data.get("content", {}).get("data", {}).get("hits", [])

            self.logger.info(f"ComplyAdvantage screen for '{subject_name}': {len(hits)} hit(s)")

            return {
                "status": "HIT" if hits else "CLEAR",
                "provider": "ComplyAdvantage",
                "matches": [
                    {
                        "name": h.get("doc", {}).get("name"),
                        "match_types": h.get("match_types"),
                        "score": h.get("score"),
                    }
                    for h in hits
                ],
            }
        except Exception as e:
            self.logger.error(f"ComplyAdvantage screening failed for '{subject_name}': {e}")
            raise Exception(f"Sanctions screening failed: {str(e)}")


# A handful of names/terms drawn from OFAC's published sample/test data, used so demos and
# tests can reliably trigger a HIT without a real watchlist. Never used to decide anything
# in production — MockSanctionsScreeningClient only runs when USE_REAL_SCREENING is unset.
_MOCK_WATCHLIST_TERMS = [
    "OFAC TEST",
    "SPECIALLY DESIGNATED NATIONAL",
    "SANCTIONED ENTITY",
    "BLOCKED PERSON",
]


class MockSanctionsScreeningClient(SanctionsScreeningClient):
    """Deterministic mock screening client for sandbox/demo/testing.

    Flags a name as a HIT only if it contains one of a small set of obvious
    test markers, so ordinary demo data always screens CLEAR.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Using MockSanctionsScreeningClient")

    def screen(self, subject_name: str) -> Dict[str, Any]:
        normalized = subject_name.upper()
        matched_terms = [term for term in _MOCK_WATCHLIST_TERMS if term in normalized]

        if matched_terms:
            return {
                "status": "HIT",
                "provider": "MockSanctionsScreening",
                "matches": [{"name": subject_name, "match_types": matched_terms, "score": 1.0}],
            }

        return {"status": "CLEAR", "provider": "MockSanctionsScreening", "matches": []}


def get_screening_client() -> SanctionsScreeningClient:
    """Factory function to get the appropriate sanctions screening client."""
    use_real = os.getenv("USE_REAL_SCREENING", "False").lower() in ["true", "1"]

    if use_real:
        return ComplyAdvantageClient()
    else:
        return MockSanctionsScreeningClient()
