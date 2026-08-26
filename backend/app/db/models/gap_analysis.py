"""ORM model for the application-focused gap analysis artefact."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class GapAnalysisModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "gap_analyses"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("application_workspaces.id", ondelete="CASCADE")
    )
    job_analysis_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("job_analyses.id", ondelete="CASCADE")
    )
    coverage: Mapped[list] = mapped_column(JSONB, default=list)
    gap_strategies: Mapped[list] = mapped_column(JSONB, default=list)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
