"""Data access for the single stored Gmail OAuth credential.

Same singleton-row pattern as AppSettingsRepository, except there is no
lazy "create with defaults" - a row only ever exists once the user has
actually connected an account (see GmailAuthService.exchange_code)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models.gmail_credential import GmailCredentialModel
from app.domain.gmail_credential import GmailCredential


def _to_domain(model: GmailCredentialModel) -> GmailCredential:
    return GmailCredential(
        connected_email=model.connected_email,
        refresh_token_encrypted=model.refresh_token_encrypted,
        access_token_encrypted=model.access_token_encrypted,
        access_token_expires_at=model.access_token_expires_at,
        connected_at=model.connected_at,
        last_sync_at=model.last_sync_at,
        last_sync_status=model.last_sync_status,
        last_sync_message=model.last_sync_message,
    )


class GmailCredentialRepository:
    def get(self, db: Session) -> GmailCredential | None:
        model = db.query(GmailCredentialModel).first()
        return _to_domain(model) if model else None

    def _get_model(self, db: Session) -> GmailCredentialModel | None:
        return db.query(GmailCredentialModel).first()

    def save(self, db: Session, credential: GmailCredential) -> GmailCredential:
        """Upserts the single row - a fresh connect (or reconnect, e.g. after
        `disconnect`) always replaces whatever was there before."""
        model = self._get_model(db)
        if model is None:
            model = GmailCredentialModel()
            db.add(model)
        model.connected_email = credential.connected_email
        model.refresh_token_encrypted = credential.refresh_token_encrypted
        model.access_token_encrypted = credential.access_token_encrypted
        model.access_token_expires_at = credential.access_token_expires_at
        model.connected_at = credential.connected_at
        model.last_sync_at = credential.last_sync_at
        model.last_sync_status = credential.last_sync_status
        model.last_sync_message = credential.last_sync_message
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def set_access_token(
        self, db: Session, *, access_token_encrypted: str, expires_at: datetime
    ) -> GmailCredential | None:
        model = self._get_model(db)
        if model is None:
            return None
        model.access_token_encrypted = access_token_encrypted
        model.access_token_expires_at = expires_at
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def set_last_sync(
        self, db: Session, *, last_sync_at: datetime, status: str, message: str | None
    ) -> GmailCredential | None:
        model = self._get_model(db)
        if model is None:
            return None
        model.last_sync_at = last_sync_at
        model.last_sync_status = status
        model.last_sync_message = message
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def delete(self, db: Session) -> bool:
        model = self._get_model(db)
        if model is None:
            return False
        db.delete(model)
        db.commit()
        return True
