"""Unit tests for GmailAuthService - token exchange/refresh is mocked via
httpx.MockTransport; encryption round-trips through a real Fernet key."""

from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.services.gmail_auth_service import GmailAuthService, TokenExchangeError


def _fake_settings(**overrides) -> Settings:
    defaults = dict(
        google_oauth_client_id="test-client-id",
        google_oauth_client_secret="test-client-secret",
        google_oauth_redirect_uri="http://localhost:8000/api/gmail/oauth/callback",
        secret_key=Fernet.generate_key().decode(),
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _service(handler=None, *, settings: Settings | None = None) -> GmailAuthService:
    transport = httpx.MockTransport(handler) if handler else None
    client = httpx.Client(transport=transport) if transport else None
    return GmailAuthService(client=client)


def test_encrypt_decrypt_round_trip(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)
    service = _service()
    encrypted = service.encrypt("a-refresh-token")
    assert encrypted != "a-refresh-token"
    assert service.decrypt(encrypted) == "a-refresh-token"


def test_decrypt_with_wrong_key_raises_token_exchange_error(monkeypatch):
    settings_a = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings_a)
    encrypted = _service().encrypt("a-refresh-token")

    settings_b = _fake_settings(secret_key=Fernet.generate_key().decode())
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings_b)
    with pytest.raises(TokenExchangeError):
        _service().decrypt(encrypted)


def test_build_authorize_url_requests_readonly_scope(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)
    url = _service().build_authorize_url(state="abc123")
    assert "gmail.readonly" in url
    assert "state=abc123" in url
    assert "access_type=offline" in url


def test_build_authorize_url_without_client_id_raises(monkeypatch):
    settings = _fake_settings(google_oauth_client_id="")
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)
    with pytest.raises(RuntimeError):
        _service().build_authorize_url(state="abc123")


def test_exchange_code_success(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "access_token": "access-123",
                    "refresh_token": "refresh-456",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(200, json={"email": "candidate@example.com"})

    tokens = _service(handler).exchange_code("auth-code")
    assert tokens.access_token == "access-123"
    assert tokens.refresh_token == "refresh-456"
    assert tokens.connected_email == "candidate@example.com"


def test_exchange_code_without_refresh_token_raises(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "access-123", "expires_in": 3600})

    with pytest.raises(TokenExchangeError):
        _service(handler).exchange_code("auth-code")


def test_exchange_code_rejected_by_google_raises(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid_grant")

    with pytest.raises(TokenExchangeError):
        _service(handler).exchange_code("bad-code")


def test_refresh_access_token_success(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr("app.services.gmail_auth_service.get_settings", lambda: settings)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})

    access_token, expires_at = _service(handler).refresh_access_token("refresh-456")
    assert access_token == "new-access"
    assert expires_at is not None
