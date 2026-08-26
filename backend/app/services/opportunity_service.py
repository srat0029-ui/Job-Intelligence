"""Builds the ranked "opportunity feed" (Discover page) from discovered
jobs + their linked analyses.

Filtering, sorting, and pagination all happen in SQL now
(`DiscoveredJobRepository.list_paginated`), relying on
`latest_overall_score`/`latest_recommendation`/`latest_priority` being kept
denormalised on the `discovered_jobs` row itself right after analysis (see
DiscoveryService.promote_and_analyze) - the feed query never joins
`job_analyses` for the list itself. The only per-page (not per-table) work
left in Python is fetching the small amount of *richer* per-item detail
(why-this-job bullets, strong matches, main gap) that genuinely doesn't
belong denormalised onto every row - bounded to `page_size` items, not the
whole table.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.discovery import DiscoveredJob
from app.domain.enums import (
    ApplicationStatus,
    DiscoveredJobStatus,
    EvidenceTier,
    JobPriority,
    Recommendation,
)
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.repositories.job_repository import JobRepository
from app.services.priority_service import build_why_summary

# Statuses hidden from the feed by default - a "rejected"/duplicate job
# clutters the thing the user actually wants to see (jobs worth acting on),
# but nothing is deleted; `include_rejected=True` still surfaces them.
DEFAULT_HIDDEN_STATUSES = [DiscoveredJobStatus.DUPLICATE, DiscoveredJobStatus.PREFILTER_REJECTED]


class OpportunityItem(BaseModel):
    discovered_job_id: UUID
    job_id: UUID | None
    title: str
    company: str
    location: str | None
    status: DiscoveredJobStatus
    prefilter_reason: str | None
    search_profile_id: UUID | None
    published_at: datetime | None
    discovered_at: datetime | None
    overall_score: float | None
    recommendation: Recommendation | None
    priority: JobPriority | None
    strong_matches: list[str]
    main_gap: str | None
    why_summary: list[str]
    application_status: ApplicationStatus | None
    source_url: str | None
    reviewed_at: datetime | None


class OpportunityPage(BaseModel):
    items: list[OpportunityItem]
    total: int
    page: int
    page_size: int


class OpportunityService:
    def __init__(
        self,
        discovered_job_repository: DiscoveredJobRepository | None = None,
        job_repository: JobRepository | None = None,
        analysis_repository: AnalysisRepository | None = None,
    ) -> None:
        self._discovered_job_repository = discovered_job_repository or DiscoveredJobRepository()
        self._job_repository = job_repository or JobRepository()
        self._analysis_repository = analysis_repository or AnalysisRepository()

    def list_opportunities(
        self,
        db: Session,
        *,
        sort_by: str = "score",
        descending: bool = True,
        status: DiscoveredJobStatus | None = None,
        search_profile_id: UUID | None = None,
        include_rejected: bool = False,
        analysed_only: bool = False,
        reviewed: bool | None = None,
        min_score: float | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OpportunityPage:
        exclude_statuses = (
            None if (include_rejected or status is not None) else DEFAULT_HIDDEN_STATUSES
        )

        discovered_jobs, total = self._discovered_job_repository.list_paginated(
            db,
            status=status,
            exclude_statuses=exclude_statuses,
            search_profile_id=search_profile_id,
            min_score=min_score,
            analysed_only=analysed_only,
            reviewed=reviewed,
            sort_by=sort_by,
            descending=descending,
            page=page,
            page_size=page_size,
        )

        job_ids = [d.job_id for d in discovered_jobs if d.job_id is not None]
        jobs_by_id = self._job_repository.get_many(db, job_ids)

        items = [
            self._to_item(d, jobs_by_id.get(d.job_id) if d.job_id else None, db)
            for d in discovered_jobs
        ]
        return OpportunityPage(items=items, total=total, page=page, page_size=page_size)

    def _to_item(self, d, job, db: Session) -> OpportunityItem:
        strong_matches: list[str] = []
        main_gap: str | None = None
        why_summary: list[str] = []

        if job is not None and d.status == DiscoveredJobStatus.ANALYSED:
            analysis = self._analysis_repository.get_latest_for_job(db, job.id)
            if analysis is not None:
                strong_matches = [
                    m.requirement_name
                    for m in analysis.match_result.matches
                    if m.tier == EvidenceTier.EXPLICIT and not m.is_gap
                ][:4]
                gaps = [m.requirement_name for m in analysis.match_result.matches if m.is_gap]
                main_gap = gaps[0] if gaps else None
                why_summary = build_why_summary(analysis)

        return OpportunityItem(
            discovered_job_id=d.id,  # type: ignore[arg-type]
            job_id=d.job_id,
            title=d.title,
            company=d.company,
            location=d.location,
            status=d.status,
            prefilter_reason=d.prefilter_reason,
            search_profile_id=d.search_profile_id,
            published_at=d.published_at,
            discovered_at=d.created_at,
            overall_score=d.latest_overall_score,
            recommendation=(
                Recommendation(d.latest_recommendation) if d.latest_recommendation else None
            ),
            priority=JobPriority(d.latest_priority) if d.latest_priority else None,
            strong_matches=strong_matches,
            main_gap=main_gap,
            why_summary=why_summary,
            application_status=job.application_status if job else None,
            source_url=d.source_url,
            reviewed_at=d.reviewed_at,
        )

    def mark_reviewed(self, db: Session, discovered_job_id: UUID) -> DiscoveredJob | None:
        return self._discovered_job_repository.mark_reviewed(db, discovered_job_id)

    def ignore(self, db: Session, discovered_job_id: UUID) -> DiscoveredJob | None:
        """"Ignore" for a job that hasn't (or won't) be promoted/analysed -
        reuses the existing ARCHIVED status. A promoted job already has the
        richer `ApplicationStatus.IGNORED` available via
        PUT /api/jobs/{id}/status."""
        return self._discovered_job_repository.archive(db, discovered_job_id)
