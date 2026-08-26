"""Domain models for automated job discovery.

`DiscoveredJob` is the canonical, source-agnostic representation every
`JobSource` normalises into (see app/ingestion/job_source.py for the raw
per-posting shape) and the working record the discovery pipeline tracks
through dedup -> pre-filter -> analysis. It is deliberately separate from
the existing `Job` table: `Job` represents "a posting the user is actively
analysing" (manual paste, or promoted from discovery); `DiscoveredJob` is
the audit trail of everything a discovery run ever saw, including jobs that
never became a `Job` at all (duplicates, pre-filter rejections). Once a
DiscoveredJob is promoted, `job_id` links to the `Job` row that the
existing, unmodified extraction/matching/scoring pipeline operates on.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import DiscoveredJobStatus, DiscoveryRunStatus, JobSourceType, SeniorityLevel


class DiscoveredJob(BaseModel):
    id: UUID | None = None
    source: JobSourceType
    external_id: str | None = None
    source_url: str | None = None
    title: str
    company: str
    raw_description: str
    location: str | None = None
    remote_type: str | None = None  # "remote" | "hybrid" | "onsite" | None (unknown)
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    employment_type: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    source_metadata: dict = Field(default_factory=dict)

    dedupe_fingerprint: str | None = None
    status: DiscoveredJobStatus = DiscoveredJobStatus.DISCOVERED
    prefilter_reason: str | None = None
    search_profile_id: UUID | None = None
    discovery_run_id: UUID | None = None
    job_id: UUID | None = None  # set once promoted into the `jobs` table

    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    times_seen: int = 1

    created_at: datetime | None = None
    updated_at: datetime | None = None


class SearchProfile(BaseModel):
    """A saved, named search configuration for automated discovery.

    `max_experience_level` reuses the existing `SeniorityLevel` enum rather
    than inventing a parallel concept - "early career" maps to `graduate`,
    and the pre-filter rejects postings whose extracted/inferred seniority
    is clearly above this ceiling.
    """

    id: UUID | None = None
    name: str
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    include_remote: bool = True
    max_experience_level: SeniorityLevel | None = None
    excluded_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    # Per-source tuning, e.g. {"adzuna": {"results_per_page": 50, "max_pages": 3}}
    source_config: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DiscoveryRunCounts(BaseModel):
    retrieved: int = 0
    new: int = 0
    duplicates: int = 0
    prefilter_rejected: int = 0
    eligible: int = 0
    analysed: int = 0
    deferred: int = 0
    failed: int = 0
    strong_apply_or_better: int = 0


class DiscoveryRun(BaseModel):
    id: UUID | None = None
    status: DiscoveryRunStatus = DiscoveryRunStatus.RUNNING
    search_profile_ids: list[UUID] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    counts: DiscoveryRunCounts = Field(default_factory=DiscoveryRunCounts)
    estimated_cost_usd: float = 0.0
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
