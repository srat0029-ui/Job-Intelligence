"""ORM model for a completed job analysis (extraction + matching + score).

The extracted job, requirement matches, and score breakdown are stored as
validated JSONB blobs - the Pydantic schemas in app.domain are the source of
truth for their shape, and every read/write round-trips through them, so this
is not "unvalidated free text", just a nested structure that doesn't benefit
from being exploded into a dozen more tables for a single-candidate V1 tool.
`overall_score` and `recommendation` are pulled out as real columns because
the dashboard needs to sort/filter/aggregate on them directly.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class JobAnalysisModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "job_analyses"

    job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    extracted_job: Mapped[dict] = mapped_column(JSONB)
    match_result: Mapped[dict] = mapped_column(JSONB)
    fit_score: Mapped[dict] = mapped_column(JSONB)
    overall_score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(50))
