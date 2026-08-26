"""Orchestrates one end-to-end discovery run:

    job sources -> normalisation -> deduplication -> deterministic pre-filter
    -> AI extraction -> evidence matching -> deterministic scoring
    -> prioritised opportunity

This is deliberately a *coordinator*, not a second analysis system: once a
posting survives dedup + pre-filter, it is promoted into the existing
`jobs` table and handed to the existing, unmodified `AnalysisOrchestrator`
(extraction -> matching -> scoring). Nothing about how a job gets analysed
changes here - only how it gets *discovered* and *whether it's worth
analysing at all*.

Cost control lives here, not in AnalysisOrchestrator: `AppSettings` gates
whether AI analysis runs automatically at all, caps how many jobs one run
will analyse, and (if a daily budget is set) stops analysing once today's
spend would exceed it. A job past those limits is left `awaiting_analysis`,
not silently dropped - `POST /discovery/discovered-jobs/{id}/analyze` (see
routes) can always force it by hand.

One failed analysis is caught and recorded per-job (`analysis_failed` +
the error in `source_metadata`) and never aborts the run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.base import LLMProvider
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.discovery import DiscoveredJobModel
from app.domain.app_settings import AppSettings
from app.domain.candidate import Candidate
from app.domain.discovery import DiscoveryRun, DiscoveryRunCounts, SearchProfile
from app.domain.enums import DiscoveredJobStatus, DiscoveryRunStatus, JobPriority, JobSourceType
from app.domain.job import Job
from app.ingestion.adzuna_source import AdzunaJobSource, AdzunaSearchConfig
from app.ingestion.job_source import JobSource, RawJobPosting
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.app_settings_repository import AppSettingsRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.repositories.discovery_run_repository import DiscoveryRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.search_profile_repository import SearchProfileRepository
from app.services import deduplication_service
from app.services.analysis_orchestrator import AnalysisOrchestrator, CandidateProfileMissingError
from app.services.prefilter_service import evaluate_prefilter
from app.services.priority_service import classify_priority

logger = get_logger(__name__)

SourceBuilder = Callable[[SearchProfile], JobSource | None]


class NoSearchProfilesError(Exception):
    pass


def _posting_from_discovered(discovered_job: DiscoveredJobModel) -> RawJobPosting:
    return RawJobPosting(
        title=discovered_job.title,
        company=discovered_job.company,
        location=discovered_job.location,
        source_url=discovered_job.source_url,
        source_type=JobSourceType(discovered_job.source),
        raw_description=discovered_job.raw_description,
    )


class DiscoveryService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        source_builders: list[SourceBuilder] | None = None,
        candidate_repository: CandidateRepository | None = None,
        search_profile_repository: SearchProfileRepository | None = None,
        discovered_job_repository: DiscoveredJobRepository | None = None,
        discovery_run_repository: DiscoveryRunRepository | None = None,
        job_repository: JobRepository | None = None,
        ai_trace_repository: AITraceRepository | None = None,
        app_settings_repository: AppSettingsRepository | None = None,
        analysis_orchestrator: AnalysisOrchestrator | None = None,
    ) -> None:
        self._candidate_repository = candidate_repository or CandidateRepository()
        self._search_profile_repository = search_profile_repository or SearchProfileRepository()
        self._discovered_job_repository = discovered_job_repository or DiscoveredJobRepository()
        self._discovery_run_repository = discovery_run_repository or DiscoveryRunRepository()
        self._job_repository = job_repository or JobRepository()
        self._ai_trace_repository = ai_trace_repository or AITraceRepository()
        self._app_settings_repository = app_settings_repository or AppSettingsRepository()
        self._analysis_orchestrator = analysis_orchestrator or AnalysisOrchestrator(llm_provider)
        # A list, not a single source, so a future Lever/Greenhouse adapter
        # is one more entry here - not a rewrite of the run loop.
        self._source_builders = source_builders or [self._build_adzuna_source]

    def _build_adzuna_source(self, profile: SearchProfile) -> JobSource | None:
        settings = get_settings()
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            logger.warning("adzuna_not_configured", profile=profile.name)
            return None
        adzuna_cfg = profile.source_config.get("adzuna", {})
        config = AdzunaSearchConfig(
            keywords=profile.keywords,
            locations=profile.locations,
            results_per_page=adzuna_cfg.get("results_per_page", 50),
            max_pages=adzuna_cfg.get("max_pages", 1),
            max_days_old=adzuna_cfg.get("max_days_old"),
        )
        return AdzunaJobSource(
            app_id=settings.adzuna_app_id,
            app_key=settings.adzuna_app_key,
            config=config,
            country=settings.adzuna_country,
        )

    def run(self, db: Session, *, search_profile_ids: list[UUID] | None = None) -> DiscoveryRun:
        candidate = self._candidate_repository.get_singleton(db)
        if candidate is None:
            raise CandidateProfileMissingError(
                "No candidate profile exists yet - seed or create one before running discovery."
            )

        if search_profile_ids:
            profiles = [
                p
                for pid in search_profile_ids
                if (p := self._search_profile_repository.get(db, pid)) is not None
            ]
        else:
            profiles = self._search_profile_repository.list_enabled(db)

        if not profiles:
            raise NoSearchProfilesError("No enabled search profiles to run discovery with.")

        app_settings = self._app_settings_repository.get(db)
        source_names = sorted({b.__name__ for b in self._source_builders})
        run_model = self._discovery_run_repository.start(
            db, search_profile_ids=[p.id for p in profiles if p.id], sources_used=source_names
        )
        counts = DiscoveryRunCounts()

        try:
            for profile in profiles:
                self._discover_for_profile(db, profile, candidate, run_model.id, counts)
            db.commit()

            if app_settings.auto_ai_analysis_enabled:
                self._run_analysis_phase(db, run_model.id, app_settings, counts)
            else:
                pending = self._discovered_job_repository.list_awaiting_analysis(
                    db, discovery_run_id=run_model.id
                )
                counts.deferred += len(pending)
            db.commit()

            run_job_ids = self._job_ids_analysed_this_run(db, run_model.id)
            estimated_cost = self._ai_trace_repository.sum_cost_for_input_identifiers(
                db, [str(j) for j in run_job_ids]
            )
            return self._discovery_run_repository.finish(
                db,
                run_model,
                counts=counts,
                estimated_cost_usd=estimated_cost,
                status=DiscoveryRunStatus.COMPLETED,
            )
        except Exception as exc:  # noqa: BLE001 - last-resort net; per-job errors are already isolated below
            logger.error("discovery_run_failed", run_id=str(run_model.id), error=str(exc))
            self._discovery_run_repository.finish(
                db,
                run_model,
                counts=counts,
                estimated_cost_usd=0.0,
                status=DiscoveryRunStatus.FAILED,
                error_message=str(exc)[:2000],
            )
            raise

    def _discover_for_profile(
        self,
        db: Session,
        profile: SearchProfile,
        candidate: Candidate,
        run_id: UUID,
        counts: DiscoveryRunCounts,
    ) -> None:
        source = None
        for builder in self._source_builders:
            source = builder(profile)
            if source is not None:
                break
        if source is None:
            logger.warning("no_available_source_for_profile", profile=profile.name)
            return

        postings = source.fetch()
        counts.retrieved += len(postings)

        for posting in postings:
            existing = deduplication_service.find_duplicate(db, posting)
            if existing is not None:
                self._discovered_job_repository.mark_seen_again(db, existing)
                counts.duplicates += 1
                continue

            fingerprint = deduplication_service.compute_fingerprint(posting)
            desc_fingerprint = deduplication_service.description_fingerprint(
                posting.raw_description
            )
            discovered_model = self._discovered_job_repository.create(
                db,
                posting=posting,
                fingerprint=fingerprint,
                description_fingerprint=desc_fingerprint,
                search_profile_id=profile.id,
                discovery_run_id=run_id,
            )
            counts.new += 1

            prefilter_result = evaluate_prefilter(
                posting=posting, candidate=candidate, search_profile=profile
            )
            if not prefilter_result.passed:
                discovered_model.status = DiscoveredJobStatus.PREFILTER_REJECTED.value
                discovered_model.prefilter_reason = prefilter_result.reason
                counts.prefilter_rejected += 1
            else:
                discovered_model.status = DiscoveredJobStatus.AWAITING_ANALYSIS.value
                counts.eligible += 1
            db.flush()

    def _run_analysis_phase(
        self, db: Session, run_id: UUID, app_settings: AppSettings, counts: DiscoveryRunCounts
    ) -> None:
        awaiting = self._discovered_job_repository.list_awaiting_analysis(
            db, discovery_run_id=run_id
        )

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent_today = self._ai_trace_repository.sum_cost_since(db, today_start)
        budget = app_settings.daily_ai_analysis_budget_usd

        for i, discovered_model in enumerate(awaiting):
            if i >= app_settings.max_ai_analyses_per_run:
                counts.deferred += 1
                continue
            if budget is not None and spent_today >= budget:
                counts.deferred += 1
                continue

            try:
                job, priority = self.promote_and_analyze(db, discovered_model)
                counts.analysed += 1
                if priority in (JobPriority.APPLY_ASAP, JobPriority.STRONG_APPLY):
                    counts.strong_apply_or_better += 1
                cost = self._ai_trace_repository.sum_cost_for_input_identifiers(
                    db, [str(job.id)]
                )
                spent_today += cost
            except Exception as exc:  # noqa: BLE001 - isolate one bad job from the whole run
                logger.error(
                    "discovery_job_analysis_failed",
                    discovered_job_id=str(discovered_model.id),
                    error=str(exc),
                )
                discovered_model.status = DiscoveredJobStatus.ANALYSIS_FAILED.value
                discovered_model.source_metadata = {
                    **(discovered_model.source_metadata or {}),
                    "analysis_error": str(exc)[:500],
                }
                counts.failed += 1
                db.flush()

    def promote_and_analyze(
        self, db: Session, discovered_model: DiscoveredJobModel
    ) -> tuple[Job, JobPriority]:
        """Promotes one DiscoveredJobModel into the existing `jobs` table (if
        not already linked) and runs it through the unmodified
        AnalysisOrchestrator. Returns (Job, JobPriority). Used both by the
        automated analysis phase and by the "force analyse this one"
        manual-override endpoint."""
        if discovered_model.job_id is None:
            posting = _posting_from_discovered(discovered_model)
            job = self._job_repository.create_from_posting(db, posting)
            discovered_model.job_id = job.id
            db.flush()
        else:
            existing_job = self._job_repository.get(db, discovered_model.job_id)
            if existing_job is None:
                raise ValueError(
                    f"DiscoveredJob {discovered_model.id} references missing job "
                    f"{discovered_model.job_id}."
                )
            job = existing_job

        discovered_model.status = DiscoveredJobStatus.ANALYSING.value
        db.flush()

        assert job.id is not None
        analysis = self._analysis_orchestrator.analyze(db, job.id)
        discovered_model.status = DiscoveredJobStatus.ANALYSED.value
        db.flush()

        priority = classify_priority(analysis.fit_score.overall_score)
        return job, priority

    def _job_ids_analysed_this_run(self, db: Session, run_id: UUID) -> list[UUID]:
        models = db.execute(
            select(DiscoveredJobModel.job_id).where(
                DiscoveredJobModel.discovery_run_id == run_id,
                DiscoveredJobModel.job_id.is_not(None),
            )
        ).scalars()
        return [m for m in models if m is not None]
