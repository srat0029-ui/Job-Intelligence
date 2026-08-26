"""End-to-end tests of the discovery pipeline through the real API + real
Postgres:

    search results -> normalisation -> deduplication -> deterministic
    pre-filter -> fake LLM extraction/matching -> deterministic scoring
    -> ranked opportunity feed

Uses a FakeLLMProvider (no network/API key needed) and fake JobSources
injected via dependency overrides / factory seams (no Adzuna/Lever
credentials needed), exactly like test_analysis_workflow.py does for the
plain analysis pipeline.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai.providers.factory import get_llm_provider
from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.api.deps import get_db, get_discovery_service
from app.domain.candidate import Candidate, CandidatePreferences, Evidence
from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.enums import AIOperationType, ATSType, EvidenceTier, JobSourceType, SeniorityLevel
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.ingestion.job_source import JobSource, RawJobPosting
from app.main import app
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.company_watchlist_repository import CompanyWatchlistRepository
from app.services.discovery_service import DiscoveryService


class _FakeSource(JobSource):
    source_type = JobSourceType.ADZUNA

    def __init__(self, postings: list[RawJobPosting]) -> None:
        self._postings = postings

    def fetch(self) -> list[RawJobPosting]:
        return self._postings


def test_full_discovery_pipeline(db):
    candidate = CandidateRepository().upsert(
        db,
        Candidate(
            name="Integration Test Candidate",
            evidence=[
                Evidence(
                    source_type="project",
                    source_label="AFL Pricing Engine",
                    statement="Built a FastAPI backend with SQLAlchemy and Python.",
                    skill_tags=["python", "fastapi"],
                )
            ],
            preferences=CandidatePreferences(preferred_locations=["Melbourne"]),
        ),
    )
    evidence_id = str(candidate.evidence[0].id)

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Junior Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
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
    fake_provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.9,
                    evidence_ids=[evidence_id],
                    evidence_summary="Directly demonstrated.",
                )
            ]
        ),
    )

    postings = [
        # Eligible - should survive dedup + pre-filter and get analysed.
        RawJobPosting(
            title="Junior Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            source_type=JobSourceType.ADZUNA,
            raw_description="Junior Backend Engineer role requiring Python.",
            external_id="job-1",
        ),
        # Clearly senior - should be pre-filter rejected, never reaching the LLM.
        RawJobPosting(
            title="Senior Principal Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            source_type=JobSourceType.ADZUNA,
            raw_description="Senior Principal role requiring 12+ years experience.",
            external_id="job-2",
        ),
        # Duplicate of the first posting (same external_id) - must be deduped.
        RawJobPosting(
            title="Junior Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            source_type=JobSourceType.ADZUNA,
            raw_description="Junior Backend Engineer role requiring Python.",
            external_id="job-1",
        ),
    ]

    discovery_service = DiscoveryService(
        llm_provider=fake_provider,
        adzuna_source_factory=lambda config: _FakeSource(postings),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    app.dependency_overrides[get_discovery_service] = lambda: discovery_service
    try:
        client = TestClient(app)

        profile_resp = client.post(
            "/api/discovery/search-profiles",
            json={
                "name": "Early Career Backend",
                "keywords": ["backend engineer"],
                "locations": ["Melbourne"],
                "include_remote": True,
                "max_experience_level": SeniorityLevel.GRADUATE.value,
                "excluded_keywords": [],
                "enabled": True,
                "source_config": {},
            },
        )
        assert profile_resp.status_code == 201
        profile_id = profile_resp.json()["id"]

        run_resp = client.post("/api/discovery/run", json={"search_profile_ids": [profile_id]})
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()

        assert run["counts"]["retrieved"] == 3
        assert run["counts"]["new"] == 2  # dedup collapsed the third posting
        assert run["counts"]["duplicates"] == 1
        assert run["counts"]["prefilter_rejected"] == 1  # the senior posting
        assert run["counts"]["eligible"] == 1
        assert run["counts"]["analysed"] == 1
        assert run["estimated_cost_usd"] == 0.0  # FakeLLMProvider reports zero cost

        # Default feed view hides pre-filter-rejected jobs.
        feed_resp = client.get("/api/discovery/opportunities")
        assert feed_resp.status_code == 200
        feed = feed_resp.json()
        assert feed["total"] == 1
        opportunity = feed["items"][0]
        assert opportunity["title"] == "Junior Backend Engineer"
        assert opportunity["status"] == "analysed"
        assert opportunity["overall_score"] is not None
        assert opportunity["priority"] is not None
        assert "Python" in opportunity["strong_matches"]
        assert len(opportunity["why_summary"]) > 0

        # Rejected jobs are visible when explicitly requested.
        full_feed_resp = client.get("/api/discovery/opportunities?include_rejected=true")
        assert full_feed_resp.status_code == 200
        full_feed = full_feed_resp.json()
        assert full_feed["total"] == 2
        rejected = next(o for o in full_feed["items"] if o["status"] == "prefilter_rejected")
        assert rejected["prefilter_reason"] is not None
    finally:
        app.dependency_overrides.clear()


def test_multi_source_dedup_and_shortlist(db):
    """The PART 19 end-to-end scenario: an Adzuna result + a direct Lever
    posting for the SAME job (different source, same underlying role) +
    one genuinely distinct Lever job at the same company ->
    normalisation -> duplicate resolution (exact id, since both share the
    same external id path isn't realistic here, so this exercises the
    deterministic-fingerprint stage instead, which is the common real case
    for an aggregator vs. a direct listing with slightly different URLs) ->
    pre-filter -> analysis prioritisation -> fake LLM analysis -> existing
    evidence matching -> deterministic fit score -> ranked shortlist.

    Verifies the same job from two sources becomes ONE canonical
    opportunity while BOTH source observations are preserved.
    """
    candidate = CandidateRepository().upsert(
        db,
        Candidate(
            name="Multi Source Candidate",
            evidence=[
                Evidence(
                    source_type="project",
                    source_label="Data Project",
                    statement="Built ML pipelines in Python.",
                    skill_tags=["python", "machine learning"],
                )
            ],
        ),
    )
    evidence_id = str(candidate.evidence[0].id)

    CompanyWatchlistRepository().create(
        db,
        CompanyWatchlistEntry(
            company_name="Data Co",
            ats_type=ATSType.LEVER,
            ats_identifier="data-co",
            preferred_locations=[],
        ),
    )

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Graduate Data Scientist",
            company="Data Co",
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
    fake_provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.9,
                    evidence_ids=[evidence_id],
                    evidence_summary="Directly demonstrated.",
                )
            ]
        ),
    )

    shared_description = (
        "Graduate Data Scientist role at Data Co. Requires Python and machine learning skills."
    )

    adzuna_postings = [
        RawJobPosting(
            title="Graduate Data Scientist",
            company="Data Co",
            location="Melbourne",
            source_type=JobSourceType.ADZUNA,
            raw_description=shared_description,
            external_id="adzuna-1",
            source_url="https://adzuna.example/jobs/1",
        )
    ]
    lever_postings = [
        # Same underlying job as the Adzuna posting above, but via the
        # direct employer feed with its own id/URL - must be recognised as
        # the SAME opportunity (deterministic description-fingerprint match).
        RawJobPosting(
            title="Graduate Data Scientist",
            company="Data Co",
            location="Melbourne",
            source_type=JobSourceType.LEVER,
            raw_description=shared_description,
            external_id="lever-1",
            source_url="https://jobs.lever.co/data-co/1",
        ),
        # A genuinely different role at the same company.
        RawJobPosting(
            title="Graduate Backend Engineer",
            company="Data Co",
            location="Melbourne",
            source_type=JobSourceType.LEVER,
            raw_description="Graduate Backend Engineer role at Data Co requiring Java and SQL.",
            external_id="lever-2",
            source_url="https://jobs.lever.co/data-co/2",
        ),
    ]

    discovery_service = DiscoveryService(
        llm_provider=fake_provider,
        adzuna_source_factory=lambda config: _FakeSource(adzuna_postings),
        ats_source_factory=lambda entry: _FakeSource(lever_postings),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    app.dependency_overrides[get_discovery_service] = lambda: discovery_service
    try:
        client = TestClient(app)

        profile_resp = client.post(
            "/api/discovery/search-profiles",
            json={
                "name": "Data roles",
                "keywords": ["data scientist"],
                "locations": [],
                "include_remote": True,
                "excluded_keywords": [],
                "enabled": True,
                "source_config": {},
            },
        )
        assert profile_resp.status_code == 201

        run_resp = client.post("/api/discovery/run", json={})
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()

        # 1 (Adzuna) + 2 (Lever) retrieved; the Adzuna/Lever pair collapses
        # into one canonical job, so only 2 canonical DiscoveredJobs exist.
        assert run["counts"]["retrieved"] == 3
        assert run["counts"]["new"] == 2
        assert run["counts"]["duplicates"] == 1
        assert run["counts"]["analysed"] == 2

        feed = client.get("/api/discovery/opportunities?include_rejected=true").json()
        assert feed["total"] == 2

        merged = next(o for o in feed["items"] if o["title"] == "Graduate Data Scientist")
        # Direct Lever posting should be promoted as canonical over Adzuna.
        assert merged["source_url"] == "https://jobs.lever.co/data-co/1"

        history_resp = client.get(f"/api/discovery/runs/{run['id']}")
        assert history_resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # Both source observations survive the merge - verified directly via
    # the repository since there's no dedicated API for this yet.
    from app.repositories.discovered_job_repository import DiscoveredJobRepository

    discovered = DiscoveredJobRepository()
    canonical = next(
        d for d in discovered.list_all(db) if d.title == "Graduate Data Scientist"
    )
    observations = discovered.list_observations(db, canonical.id)
    assert {o.source.value for o in observations} == {"adzuna", "lever"}
    assert {o.external_id for o in observations} == {"adzuna-1", "lever-1"}


def test_dependency_override_isolation():
    """Sanity check that dependency_overrides is actually cleared between
    tests (guards against a previous test leaking state)."""
    assert get_db not in app.dependency_overrides
    assert get_llm_provider not in app.dependency_overrides
    assert get_discovery_service not in app.dependency_overrides
