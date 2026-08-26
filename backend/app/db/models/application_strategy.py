"""ORM model for the ApplicationStrategy artefact.

Every regeneration inserts a NEW row (version = previous + 1) rather than
overwriting - see app/repositories/application_strategy_repository.py.
Never deleted; superseded rows are marked ARCHIVED via `status`.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GenerationMetaMixin, TimestampMixin, UUIDPKMixin


class ApplicationStrategyModel(Base, UUIDPKMixin, TimestampMixin, GenerationMetaMixin):
    __tablename__ = "application_strategies"
    __table_args__ = (Index("ix_application_strategies_workspace_id", "workspace_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("application_workspaces.id", ondelete="CASCADE")
    )
    gap_analysis_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gap_analyses.id", ondelete="CASCADE")
    )
    positioning: Mapped[str] = mapped_column(Text)
    lead_evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    skills_to_emphasise: Mapped[list] = mapped_column(JSONB, default=list)
    skills_to_deemphasise: Mapped[list] = mapped_column(JSONB, default=list)
    likely_concerns: Mapped[list] = mapped_column(JSONB, default=list)
    motivation_themes: Mapped[list] = mapped_column(JSONB, default=list)
    application_priority: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recommendation: Mapped[str] = mapped_column(String(30))
    source_evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    source_research_claim_ids: Mapped[list] = mapped_column(JSONB, default=list)
