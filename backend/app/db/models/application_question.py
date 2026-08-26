"""ORM model for application-question responses.

`question_key` (a normalised hash of the question text) groups regenerations
of "the same question" within a workspace so version history is per-question,
not just per-workspace - see app/repositories/application_question_repository.py.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GenerationMetaMixin, TimestampMixin, UUIDPKMixin


class ApplicationQuestionResponseModel(Base, UUIDPKMixin, TimestampMixin, GenerationMetaMixin):
    __tablename__ = "application_question_responses"
    __table_args__ = (
        Index("ix_application_question_responses_workspace_key", "workspace_id", "question_key"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("application_workspaces.id", ondelete="CASCADE")
    )
    question_key: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(Text)
    classifications: Mapped[list] = mapped_column(JSONB, default=list)
    answered_deterministically: Mapped[bool] = mapped_column(Boolean, default=False)
    response_text: Mapped[str] = mapped_column(Text)
    source_evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    source_research_claim_ids: Mapped[list] = mapped_column(JSONB, default=list)
