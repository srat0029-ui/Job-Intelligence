"""Unit tests for DiscoveryService's orchestration behaviour: run/cost
limits, the auto-analysis toggle, deduplication across runs, and failure
isolation (one bad job must never fail the whole run).

Uses a fake JobSource (injected via `adzuna_source_factory`) so these never
touch Adzuna or the network, and a FakeLLMProvider (optionally wrapped to
fail on demand) so they never touch the real Anthropic API. Job fixtures
here deliberately use distinct titles/descriptions/companies (not just
different external ids) so fuzzy deduplication - covered separately in
test_fuzzy_deduplication.py - never accidentally collapses them and skews
these cost-control assertions.
"""

from __future__ import annotations

import uuid

from app.ai.providers.base import LLMProvider, StructuredLLMResult
from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.domain.app_settings import AppSettings
from app.domain.candidate import Candidate, Evidence
from app.domain.discovery import SearchProfile
from app.domain.enums import AIOperationType, DiscoveredJobStatus, EvidenceTier, JobSourceType
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.ingestion.job_source import JobSource, RawJobPosting
from app.repositories.app_settings_repository import AppSettingsRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.repositories.search_profile_repository import SearchProfileRepository
from app.services.discovery_service import DiscoveryService

REAL_EVIDENCE_ID = uuid.uuid4()


class _FakeSource(JobSource):
    source_type = JobSourceType.ADZUNA

    def __init__(self, postings: list[RawJobPosting]) -> None:
        self._postings = postings

    def fetch(self) -> list[RawJobPosting]:
        return self._postings


class _FlakyProvider(LLMProvider):
    """Wraps a FakeLLMProvider but raises for extraction calls whose prompt
    contains a marker string - simulates one job failing analysis."""

    def __init__(self, inner: FakeLLMProvider, fail_marker: str | None = None) -> None:
        self._inner = inner
        self._fail_marker = fail_marker

    def generate_structured(self, **kwargs) -> StructuredLLMResult:
        if (
            self._fail_marker
            and kwargs["operation_type"] == AIOperationType.JOB_EXTRACTION
            and self._fail_marker in kwargs["user_prompt"]
        ):
            raise RuntimeError("simulated extraction failure")
        return self._inner.generate_structured(**kwargs)


def _posting(title: str, external_id: str, company: str = "Acme") -> RawJobPosting:
    return RawJobPosting(
        title=title,
        company=company,
        source_type=JobSourceType.ADZUNA,
        raw_description=f"{title} at {company}. Requires Python. {external_id}-unique-marker.",
        external_id=external_id,
    )


def _seed_candidate(db) -> Candidate:
    return CandidateRepository().upsert(
        db,
        Candidate(
            name="Test Candidate",
            evidence=[
                Evidence(
                    id=REAL_EVIDENCE_ID,
                    source_type="project",
                    source_label="Project",
                    statement="Built things in Python",
                    skill_tags=["python"],
                )
            ],
        ),
    )


def _seed_profile(db) -> SearchProfile:
    return SearchProfileRepository().create(
        db, SearchProfile(name="Test Profile", keywords=["python"], locations=[])
    )


def _fake_llm_provider() -> FakeLLMProvider:
    provider = FakeLLMProvider()
    provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Python Developer",
            company="Acme",
            requirements=[
                ExtractedRequirement(
                    name="Python",
                    raw_phrase="Python",
                    category="technical_skill",
                    importance="required",
                )
            ],
        ),
    )
    provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.9,
                    evidence_ids=[str(REAL_EVIDENCE_ID)],
                    evidence_summary="Matched.",
                )
            ]
        ),
    )
    return provider


def _service(db, postings, llm_provider) -> DiscoveryService:
    return DiscoveryService(
        llm_provider=llm_provider, adzuna_source_factory=lambda config: _FakeSource(postings)
    )


def test_run_limit_defers_the_rest(db):
    _seed_candidate(db)
    profile = _seed_profile(db)
    postings = [
        _posting("Data Scientist", "0", company="Company Zero"),
        _posting("Backend Engineer", "1", company="Company One"),
        _posting("Frontend Engineer", "2", company="Company Two"),
    ]
    AppSettingsRepository().update(db, AppSettings(max_ai_analyses_per_run=1))

    service = _service(db, postings, _fake_llm_provider())
    run = service.run(db, search_profile_ids=[profile.id])

    assert run.counts.eligible == 3
    assert run.counts.analysed == 1
    assert run.counts.deferred == 2


def test_daily_budget_of_zero_defers_everything(db):
    _seed_candidate(db)
    profile = _seed_profile(db)
    postings = [_posting("Job", "1")]
    AppSettingsRepository().update(db, AppSettings(daily_ai_analysis_budget_usd=0.0))

    service = _service(db, postings, _fake_llm_provider())
    run = service.run(db, search_profile_ids=[profile.id])

    assert run.counts.analysed == 0
    assert run.counts.deferred == 1


def test_auto_analysis_disabled_leaves_jobs_awaiting(db):
    _seed_candidate(db)
    profile = _seed_profile(db)
    postings = [_posting("Job", "1")]
    AppSettingsRepository().update(db, AppSettings(auto_ai_analysis_enabled=False))

    service = _service(db, postings, _fake_llm_provider())
    run = service.run(db, search_profile_ids=[profile.id])

    assert run.counts.analysed == 0
    assert run.counts.eligible == 1

    discovered = DiscoveredJobRepository().list_all(db)
    assert discovered[0].status == DiscoveredJobStatus.AWAITING_ANALYSIS


def test_one_failed_analysis_does_not_fail_the_whole_run(db):
    _seed_candidate(db)
    profile = _seed_profile(db)
    postings = [
        _posting("Good Data Job", "1", company="Company A"),
        _posting("Bad Backend Job FAILMARKER", "2", company="Company B"),
    ]
    provider = _FlakyProvider(_fake_llm_provider(), fail_marker="FAILMARKER")

    service = _service(db, postings, provider)
    run = service.run(db, search_profile_ids=[profile.id])

    assert run.counts.analysed == 1
    assert run.counts.failed == 1

    discovered = {d.title: d for d in DiscoveredJobRepository().list_all(db)}
    assert discovered["Good Data Job"].status == DiscoveredJobStatus.ANALYSED
    assert discovered["Bad Backend Job FAILMARKER"].status == DiscoveredJobStatus.ANALYSIS_FAILED
    assert "analysis_error" in discovered["Bad Backend Job FAILMARKER"].source_metadata


def test_duplicate_across_runs_is_not_reanalyzed(db):
    _seed_candidate(db)
    profile = _seed_profile(db)
    posting = _posting("Job", "1")

    service = _service(db, [posting], _fake_llm_provider())
    first_run = service.run(db, search_profile_ids=[profile.id])
    assert first_run.counts.new == 1
    assert first_run.counts.duplicates == 0

    second_run = service.run(db, search_profile_ids=[profile.id])
    assert second_run.counts.new == 0
    assert second_run.counts.duplicates == 1
    assert second_run.counts.analysed == 0
