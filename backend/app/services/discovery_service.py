"""Orchestrates one end-to-end discovery run:

    job sources (Adzuna + watchlisted company ATS feeds) -> normalisation
    -> deduplication (exact -> deterministic -> fuzzy) -> deterministic
    pre-filter -> deterministic analysis-priority ranking -> cost-controlled
    AI extraction -> evidence matching -> deterministic scoring
    -> prioritised opportunity -> attention items

This is deliberately a *coordinator*, not a second analysis system: once a
posting survives dedup + pre-filter, it is promoted into the existing
`jobs` table and handed to the existing, unmodified `AnalysisOrchestrator`
(extraction -> matching -> scoring). Nothing about how a job gets analysed
changes here - only how it gets *discovered*, *deduplicated*, and *in what
order it's worth analysing at all*.

Broad job-board search (Adzuna, via SearchProfiles) and direct-employer
discovery (Lever/Greenhouse, via the CompanyWatchlist) are two independent
input streams feeding the SAME dedup -> pre-filter -> analysis pipeline -
see README "Broad discovery vs direct-employer discovery" for why watchlist
companies aren't tied to any one SearchProfile.

Cost control lives here, not in AnalysisOrchestrator: `AppSettings` gates
whether AI analysis runs automatically at all, caps how many jobs one run
will analyse (spending that budget on the highest `analysis_priority` jobs
first - see analysis_priority_service.py), and (if a daily budget is set)
stops analysing once today's spend would exceed it. A job past those limits
is left `awaiting_analysis`, not silently dropped -
`POST /discovery/discovered-jobs/{id}/analyze` can always force it by hand.

Failure isolation is layered: one bad source (Lever site down) never stops
another source or the rest of the run (see source_health_service.py); one
failed analysis is caught and recorded per-job (`analysis_failed` + the
error in `source_metadata`) and never aborts the run. Only one discovery
run may be `running` at a time - `run()` refuses to start a second one.
"""

from __future__ import annotations

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
from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.discovery import DiscoveryRun, DiscoveryRunCounts, SearchProfile
from app.domain.enums import (
    ATSType,
    DiscoveredJobStatus,
    DiscoveryRunStatus,
    DuplicateMatchStage,
    GeographicEligibility,
    JobPriority,
    JobSourceType,
)
from app.domain.job import Job
from app.ingestion.adzuna_source import AdzunaJobSource
from app.ingestion.greenhouse_source import GreenhouseJobSource
from app.ingestion.job_source import RawJobPosting
from app.ingestion.lever_source import LeverJobSource
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.app_settings_repository import AppSettingsRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.company_watchlist_repository import CompanyWatchlistRepository
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.repositories.discovery_run_repository import DiscoveryRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.search_profile_repository import SearchProfileRepository
from app.repositories.source_health_repository import SourceHealthRepository
from app.services import deduplication_service, location_service, search_planner
from app.services.analysis_orchestrator import AnalysisOrchestrator, CandidateProfileMissingError
from app.services.analysis_priority_service import compute_analysis_priority
from app.services.attention_service import AttentionService
from app.services.prefilter_service import evaluate_prefilter
from app.services.priority_service import classify_priority
from app.services.source_health_service import fetch_with_health_tracking

logger = get_logger(__name__)

ANALYSIS_FAILURE_ATTENTION_THRESHOLD = 2
SOURCE_UNHEALTHY_ATTENTION_THRESHOLD = 3


class NoSearchProfilesError(Exception):
    pass


class DiscoveryAlreadyRunningError(Exception):
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


def _watchlist_prefilter_profile(
    enabled_profiles: list[SearchProfile], entry: CompanyWatchlistEntry
) -> SearchProfile:
    """A watchlisted company is monitored regardless of seniority ceiling -
    the user explicitly asked to see everything from it - but hard
    excludes (technologies/industries the candidate never wants) still
    apply, pooled from every enabled search profile."""
    excluded = sorted({kw for p in enabled_profiles for kw in p.excluded_keywords})
    return SearchProfile(
        name=f"watchlist:{entry.company_name}",
        locations=entry.preferred_locations,
        include_remote=True,
        max_experience_level=None,
        excluded_keywords=excluded,
    )


class DiscoveryService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        candidate_repository: CandidateRepository | None = None,
        search_profile_repository: SearchProfileRepository | None = None,
        company_watchlist_repository: CompanyWatchlistRepository | None = None,
        discovered_job_repository: DiscoveredJobRepository | None = None,
        discovery_run_repository: DiscoveryRunRepository | None = None,
        job_repository: JobRepository | None = None,
        ai_trace_repository: AITraceRepository | None = None,
        app_settings_repository: AppSettingsRepository | None = None,
        source_health_repository: SourceHealthRepository | None = None,
        attention_service: AttentionService | None = None,
        analysis_orchestrator: AnalysisOrchestrator | None = None,
        adzuna_source_factory=None,
        ats_source_factory=None,
    ) -> None:
        self._candidate_repository = candidate_repository or CandidateRepository()
        self._search_profile_repository = search_profile_repository or SearchProfileRepository()
        self._company_watchlist_repository = (
            company_watchlist_repository or CompanyWatchlistRepository()
        )
        self._discovered_job_repository = discovered_job_repository or DiscoveredJobRepository()
        self._discovery_run_repository = discovery_run_repository or DiscoveryRunRepository()
        self._job_repository = job_repository or JobRepository()
        self._ai_trace_repository = ai_trace_repository or AITraceRepository()
        self._app_settings_repository = app_settings_repository or AppSettingsRepository()
        self._source_health_repository = source_health_repository or SourceHealthRepository()
        self._attention_service = attention_service or AttentionService()
        self._analysis_orchestrator = analysis_orchestrator or AnalysisOrchestrator(llm_provider)
        # Testing seams: replace how Adzuna/ATS JobSource instances are
        # built without touching the run loop - see tests/unit/test_discovery_service.py.
        self._adzuna_source_factory = adzuna_source_factory or self._build_adzuna_source
        self._ats_source_factory = ats_source_factory or self._build_ats_source

    def _build_adzuna_source(self, config) -> AdzunaJobSource | None:
        settings = get_settings()
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            logger.warning("adzuna_not_configured")
            return None
        return AdzunaJobSource(
            app_id=settings.adzuna_app_id,
            app_key=settings.adzuna_app_key,
            config=config,
            country=settings.adzuna_country,
        )

    def _build_ats_source(self, entry: CompanyWatchlistEntry):
        if entry.ats_type == ATSType.LEVER:
            return LeverJobSource(site=entry.ats_identifier, company_name=entry.company_name)
        if entry.ats_type == ATSType.GREENHOUSE:
            return GreenhouseJobSource(
                board_token=entry.ats_identifier, company_name=entry.company_name
            )
        return None

    def run(
        self,
        db: Session,
        *,
        search_profile_ids: list[UUID] | None = None,
        triggered_by: str = "manual",
    ) -> DiscoveryRun:
        if self._discovery_run_repository.get_running(db) is not None:
            raise DiscoveryAlreadyRunningError(
                "A discovery run is already in progress - refusing to start a second one."
            )

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

        watchlist_entries = self._company_watchlist_repository.list_enabled(db)

        if not profiles and not watchlist_entries:
            raise NoSearchProfilesError(
                "No enabled search profiles or watchlisted companies to run discovery with."
            )

        app_settings = self._app_settings_repository.get(db)
        run_model = self._discovery_run_repository.start(
            db,
            search_profile_ids=[p.id for p in profiles if p.id],
            sources_used=[],
            triggered_by=triggered_by,
        )
        counts = DiscoveryRunCounts()
        sources_used: set[str] = set()

        try:
            for profile in profiles:
                self._discover_via_adzuna(
                    db, profile, candidate, run_model.id, counts, app_settings, sources_used
                )
            for entry in watchlist_entries:
                self._discover_via_watchlist_entry(
                    db, entry, profiles, candidate, run_model.id, counts, app_settings, sources_used
                )
            self._discovery_run_repository.update_sources_used(db, run_model, sorted(sources_used))
            db.commit()

            if app_settings.auto_ai_analysis_enabled:
                self._run_analysis_phase(db, run_model.id, app_settings, counts)
            else:
                pending = self._discovered_job_repository.list_awaiting_analysis(
                    db, discovery_run_id=run_model.id
                )
                counts.deferred += len(pending)
            db.commit()

            if counts.failed >= ANALYSIS_FAILURE_ATTENTION_THRESHOLD:
                self._attention_service.notify_analysis_failures(
                    db, failed_count=counts.failed, discovery_run_id=run_model.id
                )

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
        except Exception as exc:  # noqa: BLE001 - last-resort net; per-source/per-job errors are already isolated below
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

    def _discover_via_adzuna(
        self,
        db: Session,
        profile: SearchProfile,
        candidate: Candidate,
        run_id: UUID,
        counts: DiscoveryRunCounts,
        app_settings: AppSettings,
        sources_used: set[str],
    ) -> None:
        adzuna_cfg = profile.source_config.get("adzuna", {})
        configs = search_planner.plan_adzuna_configs(
            profile,
            results_per_page=adzuna_cfg.get("results_per_page", 50),
            max_pages=adzuna_cfg.get("max_pages", 1),
            max_days_old=adzuna_cfg.get("max_days_old"),
        )
        for config in configs:
            source = self._adzuna_source_factory(config)
            if source is None:
                continue
            postings, _health = fetch_with_health_tracking(
                db, source_key="adzuna", source=source, repository=self._source_health_repository
            )
            sources_used.add("adzuna")
            postings = postings[: app_settings.max_postings_per_source_per_run]
            counts.retrieved += len(postings)
            for posting in postings:
                self._process_posting(
                    db,
                    posting=posting,
                    candidate=candidate,
                    prefilter_profile=profile,
                    search_profile_id=profile.id,
                    run_id=run_id,
                    counts=counts,
                    watchlist_entry=None,
                )

    def _discover_via_watchlist_entry(
        self,
        db: Session,
        entry: CompanyWatchlistEntry,
        enabled_profiles: list[SearchProfile],
        candidate: Candidate,
        run_id: UUID,
        counts: DiscoveryRunCounts,
        app_settings: AppSettings,
        sources_used: set[str],
    ) -> None:
        source = self._ats_source_factory(entry)
        if source is None:
            logger.warning("no_source_for_ats_type", ats_type=entry.ats_type.value)
            return

        postings, health = fetch_with_health_tracking(
            db,
            source_key=entry.source_key,
            source=source,
            repository=self._source_health_repository,
        )
        sources_used.add(entry.source_key)

        if health.consecutive_failures == SOURCE_UNHEALTHY_ATTENTION_THRESHOLD:
            self._attention_service.notify_source_unhealthy(
                db, source_key=entry.source_key, consecutive_failures=health.consecutive_failures
            )

        postings = postings[: app_settings.max_postings_per_source_per_run]
        counts.retrieved += len(postings)
        prefilter_profile = _watchlist_prefilter_profile(enabled_profiles, entry)

        for posting in postings:
            self._process_posting(
                db,
                posting=posting,
                candidate=candidate,
                prefilter_profile=prefilter_profile,
                search_profile_id=None,
                run_id=run_id,
                counts=counts,
                watchlist_entry=entry,
            )

    def _process_posting(
        self,
        db: Session,
        *,
        posting: RawJobPosting,
        candidate: Candidate,
        prefilter_profile: SearchProfile,
        search_profile_id: UUID | None,
        run_id: UUID,
        counts: DiscoveryRunCounts,
        watchlist_entry: CompanyWatchlistEntry | None,
    ) -> None:
        exact = deduplication_service.find_exact_or_fingerprint_duplicate(db, posting)
        if exact is not None:
            self._record_duplicate(db, exact.model, posting, exact.stage, 1.0, None, run_id, counts)
            return

        fuzzy = deduplication_service.find_fuzzy_duplicate(db, posting)
        if fuzzy is not None:
            self._record_duplicate(
                db, fuzzy.model, posting, DuplicateMatchStage.FUZZY, fuzzy.confidence, fuzzy.reason,
                run_id, counts,
            )
            return

        eligibility = location_service.normalize_location(
            location=posting.location,
            description=posting.raw_description,
            remote_type=posting.remote_type,
        )

        fingerprint = deduplication_service.compute_fingerprint(posting)
        desc_fingerprint = deduplication_service.description_fingerprint(posting.raw_description)
        discovered_model = self._discovered_job_repository.create(
            db,
            posting=posting,
            fingerprint=fingerprint,
            description_fingerprint=desc_fingerprint,
            search_profile_id=search_profile_id,
            discovery_run_id=run_id,
            country=eligibility.country,
            geographic_eligibility=eligibility.eligibility,
            geographic_eligibility_reason=eligibility.reason,
        )
        counts.new += 1

        if eligibility.eligibility != GeographicEligibility.ELIGIBLE:
            # The hard Australia-eligibility gate - checked before, and
            # independently of, any per-profile preference below. Reuses
            # the existing PREFILTER_REJECTED status/counts so it's
            # automatically excluded from both the analysis phase
            # (list_awaiting_analysis only pulls AWAITING_ANALYSIS) and the
            # recommended feed (DEFAULT_HIDDEN_STATUSES), with no new
            # pipeline state to maintain.
            discovered_model.status = DiscoveredJobStatus.PREFILTER_REJECTED.value
            discovered_model.prefilter_reason = eligibility.reason
            counts.prefilter_rejected += 1
            db.flush()
            return

        prefilter_result = evaluate_prefilter(
            posting=posting, candidate=candidate, search_profile=prefilter_profile
        )
        if not prefilter_result.passed:
            discovered_model.status = DiscoveredJobStatus.PREFILTER_REJECTED.value
            discovered_model.prefilter_reason = prefilter_result.reason
            counts.prefilter_rejected += 1
            db.flush()
            return

        discovered_model.status = DiscoveredJobStatus.AWAITING_ANALYSIS.value
        discovered_model.analysis_priority = compute_analysis_priority(
            posting=posting, search_profile=prefilter_profile, watchlist_entry=watchlist_entry
        )
        counts.eligible += 1
        db.flush()

        if watchlist_entry is not None:
            self._attention_service.notify_watchlist_posting(
                db,
                discovered_job_id=discovered_model.id,
                job_title=posting.title,
                company=posting.company,
            )

    def _record_duplicate(
        self,
        db: Session,
        model: DiscoveredJobModel,
        posting: RawJobPosting,
        stage: DuplicateMatchStage,
        confidence: float,
        reason: str | None,
        run_id: UUID,
        counts: DiscoveryRunCounts,
    ) -> None:
        self._discovered_job_repository.add_observation(
            db,
            discovered_job_id=model.id,
            posting=posting,
            stage=stage,
            confidence=confidence,
            reason=reason,
            discovery_run_id=run_id,
        )
        self._discovered_job_repository.mark_seen_again(db, model)
        deduplication_service.maybe_promote_canonical_fields(model, posting)
        db.flush()
        counts.duplicates += 1

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

                traces = self._ai_trace_repository.list_for_input(db, str(job.id))
                counts.ai_calls += len(traces)
                counts.ai_input_tokens += sum(t.input_tokens or 0 for t in traces)
                counts.ai_output_tokens += sum(t.output_tokens or 0 for t in traces)
                cost = sum(t.estimated_cost_usd or 0.0 for t in traces)
                spent_today += cost

                if priority == JobPriority.APPLY_ASAP:
                    self._attention_service.notify_high_priority_job(
                        db,
                        discovered_job_id=discovered_model.id,
                        job_title=job.title,
                        company=job.company,
                        priority=priority.value,
                    )
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
        priority = classify_priority(analysis.fit_score.overall_score)

        discovered_model.status = DiscoveredJobStatus.ANALYSED.value
        discovered_model.latest_overall_score = analysis.fit_score.overall_score
        discovered_model.latest_recommendation = analysis.fit_score.recommendation.value
        discovered_model.latest_priority = priority.value
        db.flush()

        return job, priority

    def _job_ids_analysed_this_run(self, db: Session, run_id: UUID) -> list[UUID]:
        models = db.execute(
            select(DiscoveredJobModel.job_id).where(
                DiscoveredJobModel.discovery_run_id == run_id,
                DiscoveredJobModel.job_id.is_not(None),
            )
        ).scalars()
        return [m for m in models if m is not None]
