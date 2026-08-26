"""ORM models for automated job discovery: search profiles, the discovered
job landing table, per-source observations, and the discovery-run audit
log. See app/domain/discovery.py for the design rationale."""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class SearchProfileModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "search_profiles"

    name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # list[{"name": str, "keywords": list[str]}] - see SearchProfile.all_keyword_groups().
    keyword_groups: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    location_priority: Mapped[dict] = mapped_column(JSONB, default=dict)
    include_remote: Mapped[bool] = mapped_column(Boolean, default=True)
    max_experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    excluded_keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_config: Mapped[dict] = mapped_column(JSONB, default=dict)


class DiscoveredJobModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "discovered_jobs"
    __table_args__ = (
        Index("ix_discovered_jobs_status_score", "status", "latest_overall_score"),
        Index("ix_discovered_jobs_created_at", "created_at"),
    )

    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    raw_description: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    remote_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    dedupe_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(30), default="discovered", index=True)
    prefilter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Deterministic pre-LLM triage score (analysis order only - never fit score).
    analysis_priority: Mapped[float | None] = mapped_column(
        Float, nullable=True, index=True
    )

    # Denormalised from the latest JobAnalysis so the feed can filter/sort/
    # paginate in SQL without joining job_analyses - see OpportunityService.
    latest_overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_recommendation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latest_priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    search_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("search_profiles.id", ondelete="SET NULL"), nullable=True
    )
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    first_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)


class SourceObservationModel(Base, UUIDPKMixin):
    """One sighting of a canonical DiscoveredJob by one source - see
    app/domain/discovery.py::SourceObservation."""

    __tablename__ = "source_observations"
    __table_args__ = (Index("ix_source_observations_discovered_job_id", "discovered_job_id"),)

    discovered_job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("discovered_jobs.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    match_stage: Mapped[str] = mapped_column(String(30))
    match_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column()
    last_seen_at: Mapped[datetime] = mapped_column()
    times_seen: Mapped[int] = mapped_column(Integer, default=1)


class DiscoveryRunModel(Base, UUIDPKMixin):
    __tablename__ = "discovery_runs"

    status: Mapped[str] = mapped_column(String(20), default="running")
    search_profile_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), default=list
    )
    sources_used: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")

    retrieved_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    prefilter_rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    analysed_count: Mapped[int] = mapped_column(Integer, default=0)
    deferred_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    strong_apply_or_better_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_calls_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ai_output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
