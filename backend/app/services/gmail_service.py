"""Thin orchestration between the Gmail OAuth routes and
GmailAuthService/GmailCredentialRepository - the actual sync/discovery
logic lives in DiscoveryService, not here (see the milestone plan: Gmail
connection is just a credential; ingestion reuses the one existing
discovery pipeline)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.gmail_credential import GmailCredential
from app.repositories.gmail_credential_repository import GmailCredentialRepository
from app.services.gmail_auth_service import GmailAuthService


class GmailStatus(BaseModel):
    connected: bool
    connected_email: str | None = None
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_message: str | None = None


class GmailService:
    def __init__(
        self,
        credential_repository: GmailCredentialRepository | None = None,
        auth_service: GmailAuthService | None = None,
    ) -> None:
        self._credential_repository = credential_repository or GmailCredentialRepository()
        self._auth_service = auth_service or GmailAuthService()

    def build_connect_url(self) -> str:
        # Single-user local app: the `state` param is generated for shape-
        # compatibility with Google's flow but not verified against a
        # stored value on callback - there is no cross-user CSRF surface
        # here (only this one local user's own browser ever initiates the
        # connect flow).
        return self._auth_service.build_authorize_url(state=secrets.token_urlsafe(16))

    def handle_callback(self, db: Session, *, code: str) -> GmailStatus:
        tokens = self._auth_service.exchange_code(code)
        credential = GmailCredential(
            connected_email=tokens.connected_email,
            refresh_token_encrypted=self._auth_service.encrypt(tokens.refresh_token),
            access_token_encrypted=self._auth_service.encrypt(tokens.access_token),
            access_token_expires_at=tokens.access_token_expires_at,
            connected_at=datetime.now(UTC),
        )
        self._credential_repository.save(db, credential)
        return self.get_status(db)

    def get_status(self, db: Session) -> GmailStatus:
        credential = self._credential_repository.get(db)
        if credential is None:
            return GmailStatus(connected=False)
        return GmailStatus(
            connected=True,
            connected_email=credential.connected_email,
            connected_at=credential.connected_at,
            last_sync_at=credential.last_sync_at,
            last_sync_status=credential.last_sync_status,
            last_sync_message=credential.last_sync_message,
        )

    def disconnect(self, db: Session) -> bool:
        return self._credential_repository.delete(db)
