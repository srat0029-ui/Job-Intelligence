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

A `DiscoveredJob` may be seen by more than one source (Adzuna AND a
company's own Lever board) - each sighting is recorded as a
`SourceObservation` linked to the one canonical `DiscoveredJob`, which keeps
whichever source's fields (URL, exact title/company text) are considered
most authoritative - see app/services/deduplication_service.py and
SOURCE_QUALITY_RANK.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import (
    DiscoveredJobStatus,
    DiscoveryRunStatus,
    DuplicateMatchStage,
    JobSourceType,
    SeniorityLevel,
)


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

    # Deterministic, pre-LLM triage score - decides analysis ORDER only, is
    # never the candidate fit score. See analysis_priority_service.py.
    analysis_priority: float | None = None

    # Denormalised from the latest JobAnalysis once analysed, purely so the
    # opportunity feed can filter/sort/paginate in SQL without joining
    # job_analyses on every request - see OpportunityService.
    latest_overall_score: float | None = None
    latest_recommendation: str | None = None
    latest_priority: str | None = None

    reviewed_at: datetime | None = None

    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    times_seen: int = 1

    created_at: datetime | None = None
    updated_at: datetime | None = None


class SourceObservation(BaseModel):
    """One sighting of a canonical DiscoveredJob by one source. Nothing is
    ever thrown away when a duplicate is found - each observation keeps its
    own source/external_id/URL so provenance is fully auditable."""

    id: UUID | None = None
    discovered_job_id: UUID
    source: JobSourceType
    external_id: str | None = None
    source_url: str | None = None
    match_stage: DuplicateMatchStage
    match_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    match_reason: str | None = None
    discovery_run_id: UUID | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    times_seen: int = 1


class KeywordGroup(BaseModel):
    """One related cluster of keyword variants for the same kind of role
    (e.g. "AI / ML", "Data"). Search profiles with a broad remit (many
    unrelated role families) group keywords this way instead of one flat
    list, so the search planner can reason about "which role families does
    this profile cover" and construct a bounded number of queries rather
    than every keyword x every location."""

    name: str
    keywords: list[str] = Field(default_factory=list)


class SearchProfile(BaseModel):
    """A saved, named search configuration for automated discovery.

    `max_experience_level` reuses the existing `SeniorityLevel` enum rather
    than inventing a parallel concept - "early career" maps to `graduate`,
    and the pre-filter rejects postings whose extracted/inferred seniority
    is clearly above this ceiling.

    `keyword_groups` is the preferred way to configure keywords for a broad
    profile; the flat `keywords` field is kept for backward compatibility
    with profiles created before this existed and for simple single-group
    cases - see app/services/search_planner.py for how the two combine.
    """

    id: UUID | None = None
    name: str
    keywords: list[str] = Field(default_factory=list)
    keyword_groups: list[KeywordGroup] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    location_priority: dict[str, int] = Field(
        default_factory=dict,
        description="Optional location -> priority rank (lower = higher priority), "
        "e.g. {'Melbourne': 1, 'Sydney': 2}. Locations not listed default to the lowest priority.",
    )
    include_remote: bool = True
    max_experience_level: SeniorityLevel | None = None
    excluded_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    # Per-source tuning, e.g. {"adzuna": {"results_per_page": 50, "max_pages": 3}}
    source_config: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def all_keyword_groups(self) -> list[KeywordGroup]:
        """Keyword groups to search, folding the legacy flat `keywords`
        field in as an unnamed group if present."""
        groups = list(self.keyword_groups)
        if self.keywords:
            groups.append(KeywordGroup(name="default", keywords=self.keywords))
        return groups


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
    ai_calls: int = 0
    ai_input_tokens: int = 0
    ai_output_tokens: int = 0


class DiscoveryRun(BaseModel):
    id: UUID | None = None
    status: DiscoveryRunStatus = DiscoveryRunStatus.RUNNING
    search_profile_ids: list[UUID] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    counts: DiscoveryRunCounts = Field(default_factory=DiscoveryRunCounts)
    estimated_cost_usd: float = 0.0
    error_message: str | None = None
    triggered_by: str = "manual"  # "manual" | "scheduled"
    started_at: datetime | None = None
    finished_at: datetime | None = None
