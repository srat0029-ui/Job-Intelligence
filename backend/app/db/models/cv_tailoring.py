"""ORM model for a CV tailoring suggestion batch (one generation = one row,
versioned per workspace like ApplicationStrategyModel)."""

import uuid

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GenerationMetaMixin, TimestampMixin, UUIDPKMixin


class CVTailoringBatchModel(Base, UUIDPKMixin, TimestampMixin, GenerationMetaMixin):
    __tablename__ = "cv_tailoring_batches"
    __table_args__ = (Index("ix_cv_tailoring_batches_workspace_id", "workspace_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("application_workspaces.id", ondelete="CASCADE")
    )
    suggestions: Mapped[list] = mapped_column(JSONB, default=list)
    section_emphasis: Mapped[list] = mapped_column(JSONB, default=list)
    source_evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
