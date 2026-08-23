import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class SecretsProvider(ABC):
    @abstractmethod
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        ...


class EnvSecretsProvider(SecretsProvider):
    """Reads secrets from process environment variables — the existing
    behavior, and the default until a real secrets backend is configured."""

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(key, default)


class VaultSecretsProvider(SecretsProvider):
    """Reads secrets from HashiCorp Vault's KV v2 engine. All of this app's
    secrets are expected as fields on one document (VAULT_SECRET_PATH), the
    standard way to store one app's secret bundle in Vault — so enabling
    this doesn't require restructuring anything, just populating that one
    document with the same keys the .env file already uses.

    The fetched document is cached in memory for VAULT_CACHE_TTL_SECONDS so
    routine secret lookups (a provider client constructed per-request) don't
    each cost a round trip to Vault, while still picking up a rotated secret
    without restarting the app.
    """

    def __init__(self):
        self.addr = os.getenv("VAULT_ADDR")
        self.token = os.getenv("VAULT_TOKEN")
        if not self.addr or not self.token:
            raise ValueError("VAULT_ADDR and VAULT_TOKEN environment variables must be set")

        self.mount = os.getenv("VAULT_KV_MOUNT", "secret")
        self.path = os.getenv("VAULT_SECRET_PATH", "apex-fintech")
        self.ttl_seconds = int(os.getenv("VAULT_CACHE_TTL_SECONDS", "300"))

        self._cache: Optional[Dict[str, str]] = None
        self._cached_at: float = 0.0
        self.logger = logging.getLogger(__name__)

    def _fetch(self) -> Dict[str, str]:
        now = time.time()
        if self._cache is not None and (now - self._cached_at) < self.ttl_seconds:
            return self._cache

        url = f"{self.addr.rstrip('/')}/v1/{self.mount}/data/{self.path}"
        try:
            response = httpx.get(url, headers={"X-Vault-Token": self.token}, timeout=10.0)
            response.raise_for_status()
            data = response.json()["data"]["data"]
        except Exception as e:
            self.logger.error(f"Failed to fetch secrets from Vault ({url}): {e}")
            if self._cache is not None:
                # Serve the stale cache rather than taking down every
                # provider-backed feature because Vault had one bad request.
                self.logger.warning("Serving stale cached secrets after a Vault fetch failure")
                return self._cache
            raise

        self._cache = data
        self._cached_at = now
        return data

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            data = self._fetch()
        except Exception:
            return default
        return data.get(key, default)


def _build_provider() -> SecretsProvider:
    backend = os.getenv("SECRETS_PROVIDER", "env").lower()
    if backend == "vault":
        return VaultSecretsProvider()
    return EnvSecretsProvider()


_provider: Optional[SecretsProvider] = None


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """The one function the rest of the app should call for a credential —
    API keys, tokens, passwords, connection strings with embedded auth.
    Non-secret configuration (feature-flag env vars, base URLs, timeouts)
    should keep using os.getenv() directly; only mix credentials into this
    path.

    Backed by EnvSecretsProvider by default (SECRETS_PROVIDER unset or
    "env") or VaultSecretsProvider when SECRETS_PROVIDER=vault — set once,
    reused for the life of the process.
    """
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider.get_secret(key, default)
