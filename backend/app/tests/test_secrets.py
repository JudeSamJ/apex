"""Tests for the pluggable secrets provider (app/secrets/provider.py)."""

import pytest
import httpx

from app.secrets.provider import EnvSecretsProvider, VaultSecretsProvider, _build_provider


def test_env_provider_reads_environment(monkeypatch):
    monkeypatch.setenv("SOME_TEST_SECRET", "value-from-env")
    provider = EnvSecretsProvider()
    assert provider.get_secret("SOME_TEST_SECRET") == "value-from-env"


def test_env_provider_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_UNSET_SECRET", raising=False)
    provider = EnvSecretsProvider()
    assert provider.get_secret("SOME_UNSET_SECRET", "fallback") == "fallback"
    assert provider.get_secret("SOME_UNSET_SECRET") is None


def test_build_provider_defaults_to_env(monkeypatch):
    monkeypatch.delenv("SECRETS_PROVIDER", raising=False)
    assert isinstance(_build_provider(), EnvSecretsProvider)


def test_build_provider_selects_vault_when_configured(monkeypatch):
    monkeypatch.setenv("SECRETS_PROVIDER", "vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    assert isinstance(_build_provider(), VaultSecretsProvider)


def test_vault_provider_requires_addr_and_token(monkeypatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    with pytest.raises(ValueError):
        VaultSecretsProvider()


def test_vault_provider_fetches_and_caches(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("VAULT_KV_MOUNT", "secret")
    monkeypatch.setenv("VAULT_SECRET_PATH", "apex-fintech")

    call_count = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        call_count["n"] += 1
        assert url == "https://vault.example.com/v1/secret/data/apex-fintech"
        assert headers == {"X-Vault-Token": "test-token"}
        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": {"data": {"STRIPE_SECRET_KEY": "sk_test_from_vault"}}}, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)

    provider = VaultSecretsProvider()
    assert provider.get_secret("STRIPE_SECRET_KEY") == "sk_test_from_vault"
    assert provider.get_secret("STRIPE_SECRET_KEY") == "sk_test_from_vault"
    # Cached — the second lookup must not hit Vault again.
    assert call_count["n"] == 1

    # A key absent from the document falls back to the given default.
    assert provider.get_secret("NOT_IN_VAULT", "default-value") == "default-value"


def test_vault_provider_falls_back_to_stale_cache_on_error(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")

    responses = [
        httpx.Response(200, json={"data": {"data": {"FOO": "bar"}}}, request=httpx.Request("GET", "https://vault.example.com")),
    ]

    def fake_get_success_then_fail(url, headers=None, timeout=None):
        if responses:
            return responses.pop()
        raise httpx.ConnectError("vault unreachable")

    monkeypatch.setattr(httpx, "get", fake_get_success_then_fail)

    provider = VaultSecretsProvider()
    provider.ttl_seconds = 0  # force every call to attempt a real fetch
    assert provider.get_secret("FOO") == "bar"
    # Vault is now "down", but the previously cached value is still served.
    assert provider.get_secret("FOO") == "bar"


def test_vault_provider_returns_default_when_never_cached_and_fetch_fails(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")

    def fake_get_always_fails(url, headers=None, timeout=None):
        raise httpx.ConnectError("vault unreachable")

    monkeypatch.setattr(httpx, "get", fake_get_always_fails)

    provider = VaultSecretsProvider()
    assert provider.get_secret("ANYTHING", "safe-default") == "safe-default"
