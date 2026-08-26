"""Builds the ranked "opportunity feed" (Discover page) from discovered
jobs + their linked analyses.

Deliberately assembled in Python after a couple of simple queries rather
than one large SQL join with dynamic sort/filter clauses - at this
project's scale (hundreds, not millions, of discovered jobs) that's both
simpler to read and easier to test than building a query builder, and it's
the same pragmatic choice already made in DashboardService.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.analysis import JobAnalysis
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
from app.services.priority_service import build_why_summary, classify_priority

# Statuses hidden from the feed by default - a "rejected" job clutters the
# thing the user actually wants to see (jobs worth acting on), but nothing
# is deleted; `include_rejected=True` still surfaces them.
DEFAULT_HIDDEN_STATUSES = {DiscoveredJobStatus.DUPLICATE, DiscoveredJobStatus.PREFILTER_REJECTED}

SORT_FIELDS = {"score", "posted_date", "discovered_date", "company", "title", "location"}


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
        min_score: float | None = None,
    ) -> list[OpportunityItem]:
        discovered_jobs = self._discovered_job_repository.list_all(db)

        job_ids = [d.job_id for d in discovered_jobs if d.job_id is not None]
        jobs_by_id = self._job_repository.get_many(db, job_ids)
        analyses = self._analysis_repository.list_all(db)
        latest_analysis_by_job: dict[UUID, JobAnalysis] = {}
        for a in analyses:
            existing = latest_analysis_by_job.get(a.job_id)
            if existing is None or (
                a.created_at and existing.created_at and a.created_at > existing.created_at
            ):
                latest_analysis_by_job[a.job_id] = a

        items: list[OpportunityItem] = []
        for d in discovered_jobs:
            if status is not None and d.status != status:
                continue
            if status is None and not include_rejected and d.status in DEFAULT_HIDDEN_STATUSES:
                continue
            if search_profile_id is not None and d.search_profile_id != search_profile_id:
                continue

            job = jobs_by_id.get(d.job_id) if d.job_id else None
            analysis = latest_analysis_by_job.get(d.job_id) if d.job_id else None

            if analysed_only and analysis is None:
                continue

            overall_score = analysis.fit_score.overall_score if analysis else None
            if min_score is not None and (overall_score is None or overall_score < min_score):
                continue

            strong_matches: list[str] = []
            main_gap: str | None = None
            why_summary: list[str] = []
            priority: JobPriority | None = None
            recommendation: Recommendation | None = None

            if analysis is not None:
                strong_matches = [
                    m.requirement_name
                    for m in analysis.match_result.matches
                    if m.tier == EvidenceTier.EXPLICIT and not m.is_gap
                ][:4]
                gaps = [m.requirement_name for m in analysis.match_result.matches if m.is_gap]
                main_gap = gaps[0] if gaps else None
                why_summary = build_why_summary(analysis)
                priority = classify_priority(analysis.fit_score.overall_score)
                recommendation = analysis.fit_score.recommendation

            items.append(
                OpportunityItem(
                    discovered_job_id=d.id,  # type: ignore[arg-type]
                    job_id=d.job_id,
                    title=job.title if job else d.title,
                    company=job.company if job else d.company,
                    location=job.location if job else d.location,
                    status=d.status,
                    prefilter_reason=d.prefilter_reason,
                    search_profile_id=d.search_profile_id,
                    published_at=d.published_at,
                    discovered_at=d.created_at,
                    overall_score=overall_score,
                    recommendation=recommendation,
                    priority=priority,
                    strong_matches=strong_matches,
                    main_gap=main_gap,
                    why_summary=why_summary,
                    application_status=job.application_status if job else None,
                    source_url=d.source_url,
                )
            )

        return self._sort(items, sort_by=sort_by, descending=descending)

    def _sort(
        self, items: list[OpportunityItem], *, sort_by: str, descending: bool
    ) -> list[OpportunityItem]:
        key_field = sort_by if sort_by in SORT_FIELDS else "score"

        def key(item: OpportunityItem):
            if key_field == "score":
                return item.overall_score if item.overall_score is not None else -1.0
            if key_field == "posted_date":
                return item.published_at or datetime.min
            if key_field == "discovered_date":
                return item.discovered_at or datetime.min
            if key_field == "company":
                return item.company.lower()
            if key_field == "title":
                return item.title.lower()
            if key_field == "location":
                return (item.location or "").lower()
            return 0

        return sorted(items, key=key, reverse=descending)
