"""ORM model for the single stored Gmail OAuth credential - see
app/domain/gmail_credential.py for why this is a dedicated table rather
than folded into AppSettings."""

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class GmailCredentialModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "gmail_credentials"

    connected_email: Mapped[str] = mapped_column(String(255))
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProcessedGmailMessageModel(Base, UUIDPKMixin, TimestampMixin):
    """Tracks Gmail message IDs already ingested so an alert email is never
    re-parsed - independent of, and in addition to, the normal job-level
    deduplication (which still runs on every extracted posting)."""

    __tablename__ = "processed_gmail_messages"

    gmail_message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    processed_at: Mapped[datetime] = mapped_column()
    jobs_extracted: Mapped[int] = mapped_column(default=0)
