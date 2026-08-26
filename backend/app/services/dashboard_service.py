"""Aggregates jobs + analyses into the dashboard view.

Read-only aggregation logic - kept out of the route handler so "what counts
as a strongest opportunity" or "how score buckets are defined" has one
testable home.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.schemas import DashboardStats, DiscoveryDashboardStats, JobListItem
from app.domain.analysis import JobAnalysis
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.app_settings_repository import AppSettingsRepository
from app.repositories.attention_repository import AttentionRepository
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.repositories.job_repository import JobRepository
from app.repositories.source_health_repository import SourceHealthRepository

SCORE_BUCKETS = [
    ("0-19", 0, 20),
    ("20-39", 20, 40),
    ("40-59", 40, 60),
    ("60-79", 60, 80),
    ("80-100", 80, 101),
]


class DashboardService:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        analysis_repository: AnalysisRepository | None = None,
        discovered_job_repository: DiscoveredJobRepository | None = None,
        source_health_repository: SourceHealthRepository | None = None,
        attention_repository: AttentionRepository | None = None,
        app_settings_repository: AppSettingsRepository | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._analysis_repository = analysis_repository or AnalysisRepository()
        self._discovered_job_repository = discovered_job_repository or DiscoveredJobRepository()
        self._source_health_repository = source_health_repository or SourceHealthRepository()
        self._attention_repository = attention_repository or AttentionRepository()
        self._app_settings_repository = app_settings_repository or AppSettingsRepository()

    @staticmethod
    def _latest_per_job(analyses: list[JobAnalysis]) -> dict[UUID, JobAnalysis]:
        latest_by_job: dict[UUID, JobAnalysis] = {}
        for a in analyses:
            existing = latest_by_job.get(a.job_id)
            is_newer = (
                existing is None
                or (a.created_at and existing.created_at and a.created_at > existing.created_at)
            )
            if is_newer:
                latest_by_job[a.job_id] = a
        return latest_by_job

    @staticmethod
    def _to_item(job, analysis: JobAnalysis | None) -> JobListItem:
        return JobListItem(
            id=str(job.id),
            title=job.title,
            company=job.company,
            location=job.location,
            created_at=job.created_at,
            latest_overall_score=analysis.fit_score.overall_score if analysis else None,
            latest_recommendation=analysis.fit_score.recommendation.value if analysis else None,
            application_status=job.application_status,
            source_url=job.source_url,
        )

    def get_stats(self, db: Session) -> DashboardStats:
        jobs = self._job_repository.list_all(db)
        analyses = self._analysis_repository.list_all(db)
        jobs_by_id = {j.id: j for j in jobs}
        latest_by_job = self._latest_per_job(analyses)

        def to_item(job_id: UUID, analysis: JobAnalysis | None = None) -> JobListItem | None:
            job = jobs_by_id.get(job_id)
            return None if job is None else self._to_item(job, analysis)

        strongest = sorted(
            latest_by_job.values(), key=lambda a: a.fit_score.overall_score, reverse=True
        )[:5]
        recent = sorted(analyses, key=lambda a: a.created_at or datetime.min, reverse=True)[:5]

        distribution = {label: 0 for label, _, _ in SCORE_BUCKETS}
        for a in latest_by_job.values():
            score = a.fit_score.overall_score
            for label, low, high in SCORE_BUCKETS:
                if low <= score < high:
                    distribution[label] += 1
                    break

        return DashboardStats(
            total_jobs=len(jobs),
            total_analyses=len(analyses),
            strongest_opportunities=[
                item for a in strongest if (item := to_item(a.job_id, a)) is not None
            ],
            recent_analyses=[item for a in recent if (item := to_item(a.job_id, a)) is not None],
            score_distribution=distribution,
        )

    def list_prioritized(self, db: Session) -> list[JobListItem]:
        """Every job the user has entered, sorted by latest fit score
        (highest first); jobs never analysed sort to the bottom. This backs
        the Analysis/prioritisation page - "which jobs should I apply for?"."""
        jobs = self._job_repository.list_all(db)
        analyses = self._analysis_repository.list_all(db)
        latest_by_job = self._latest_per_job(analyses)

        items = [
            self._to_item(job, latest_by_job.get(job.id) if job.id else None) for job in jobs
        ]
        items.sort(
            key=lambda item: item.latest_overall_score
            if item.latest_overall_score is not None
            else -1,
            reverse=True,
        )
        return items

    def get_discovery_dashboard(self, db: Session) -> DiscoveryDashboardStats:
        """Discovery-side stats, unlike `get_stats` above, are sourced with
        SQL COUNT queries against `discovered_jobs` (which can genuinely
        grow large) rather than loading rows into Python - see
        DiscoveredJobRepository.count_created_since/count_high_priority_unreviewed."""
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        settings = self._app_settings_repository.get(db)
        return DiscoveryDashboardStats(
            new_jobs_today=self._discovered_job_repository.count_created_since(db, today_start),
            high_priority_unreviewed=self._discovered_job_repository.count_high_priority_unreviewed(db),
            unread_attention_count=self._attention_repository.count_unread(db),
            auto_discovery_enabled=settings.auto_discovery_enabled,
            last_scheduled_run_at=settings.last_scheduled_run_at,
            next_scheduled_run_at=settings.next_scheduled_run_at,
            source_health=self._source_health_repository.list_all(db),
        )
