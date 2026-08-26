"""ORM models for evidence-grounded company/role research.

`research_claims.research_source_id` is a real FK (CASCADE) - a claim never
outlives the source it was grounded in. `raw_text_excerpt` on
`ResearchSourceModel` is bounded (see MAX_FETCH_TEXT_CHARS in
app/ingestion/research_provider.py), not an unbounded page dump.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ResearchSourceModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "research_sources"
    __table_args__ = (Index("ix_research_sources_company_name", "company_name"),)

    company_name: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(2000))
    domain: Mapped[str] = mapped_column(String(300))
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50))
    source_quality: Mapped[str] = mapped_column(String(20))
    fetch_status: Mapped[str] = mapped_column(String(20))
    raw_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchClaimModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "research_claims"
    __table_args__ = (Index("ix_research_claims_company_name", "company_name"),)

    research_source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research_sources.id", ondelete="CASCADE")
    )
    company_name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(50))
    claim: Mapped[str] = mapped_column(Text)
    supporting_excerpt: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
