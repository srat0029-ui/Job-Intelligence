"""Gmail OAuth: authorize-URL construction, code<->token exchange, access
token refresh, and at-rest encryption of the stored refresh token.

Implemented as raw `httpx` calls against Google's REST endpoints rather than
`google-auth`/`google-auth-oauthlib`/`google-api-python-client` - see the
milestone plan for the trade-off. This app makes exactly two kinds of Google
API calls (token exchange/refresh, and Gmail message search/fetch in
gmail_client.py); a general-purpose SDK is more machinery than that needs.

Scope requested is `gmail.readonly` - the minimum needed to search and read
messages. Nothing here can modify, delete, or mark messages read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel

from app.core.config import get_settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class TokenExchangeError(Exception):
    """Google rejected the authorization code, or a refresh token is invalid
    (e.g. the user revoked access) - the caller should surface a clear
    "reconnect Gmail" message rather than a generic 500."""


class GmailTokens(BaseModel):
    connected_email: str
    refresh_token: str
    access_token: str
    access_token_expires_at: datetime


class GmailAuthService:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=15.0)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _fernet(self) -> Fernet:
        settings = get_settings()
        if not settings.secret_key:
            raise RuntimeError(
                "SECRET_KEY is not configured - cannot encrypt/decrypt the stored Gmail "
                "credential. Generate one with: python -c \"from cryptography.fernet import "
                'Fernet; print(Fernet.generate_key().decode())"'
            )
        return Fernet(settings.secret_key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet().decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise TokenExchangeError(
                "Stored Gmail credential could not be decrypted (SECRET_KEY changed?) - "
                "reconnect Gmail."
            ) from exc

    def build_authorize_url(self, *, state: str) -> str:
        settings = get_settings()
        if not settings.google_oauth_client_id:
            raise RuntimeError(
                "GOOGLE_OAUTH_CLIENT_ID is not configured - see Settings for the one-time "
                "Google Cloud setup steps."
            )
        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": f"{GMAIL_READONLY_SCOPE} openid email",
            "access_type": "offline",
            # Forces Google to always return a refresh token, even if the
            # user has previously granted consent - without this, a
            # reconnect after a revoke can silently omit it.
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> GmailTokens:
        settings = get_settings()
        response = self._client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if response.status_code >= 400:
            raise TokenExchangeError(f"Google rejected the authorization code: {response.text}")
        data = response.json()
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            raise TokenExchangeError(
                "Google did not return a refresh token - this can happen on a repeat "
                "connect without revoking prior access first. Revoke access at "
                "https://myaccount.google.com/permissions and try connecting again."
            )
        access_token = data["access_token"]
        expires_at = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600))
        email = self._fetch_email(access_token)
        return GmailTokens(
            connected_email=email,
            refresh_token=refresh_token,
            access_token=access_token,
            access_token_expires_at=expires_at,
        )

    def refresh_access_token(self, refresh_token: str) -> tuple[str, datetime]:
        settings = get_settings()
        response = self._client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code >= 400:
            raise TokenExchangeError(
                f"Failed to refresh the Gmail access token - reconnect Gmail: {response.text}"
            )
        data = response.json()
        expires_at = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600))
        return data["access_token"], expires_at

    def _fetch_email(self, access_token: str) -> str:
        response = self._client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if response.status_code >= 400:
            return "unknown"
        return response.json().get("email", "unknown")
