"""ORM model for the internal attention/notification system (see
app/domain/attention.py)."""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class AttentionItemModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "attention_items"
    __table_args__ = (Index("ix_attention_items_status", "status"),)

    item_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    related_discovered_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("discovered_jobs.id", ondelete="CASCADE"), nullable=True
    )
    related_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True
    )
    related_company: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="unread")
