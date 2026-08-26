"""ORM model for generated cover letters (versioned per workspace)."""

import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GenerationMetaMixin, TimestampMixin, UUIDPKMixin


class CoverLetterModel(Base, UUIDPKMixin, TimestampMixin, GenerationMetaMixin):
    __tablename__ = "cover_letters"
    __table_args__ = (Index("ix_cover_letters_workspace_id", "workspace_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("application_workspaces.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text)
    source_evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    source_research_claim_ids: Mapped[list] = mapped_column(JSONB, default=list)
