"""End-to-end test of the discovery pipeline through the real API + real
Postgres:

    search results -> normalisation -> deduplication -> deterministic
    pre-filter -> fake LLM extraction/matching -> deterministic scoring
    -> ranked opportunity feed

Uses a FakeLLMProvider (no network/API key needed) and a fake JobSource
injected via a dependency override (no Adzuna credentials needed), exactly
like test_analysis_workflow.py does for the plain analysis pipeline.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai.providers.factory import get_llm_provider
from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.api.deps import get_db, get_discovery_service
from app.domain.candidate import Candidate, CandidatePreferences, Evidence
from app.domain.enums import AIOperationType, EvidenceTier, JobSourceType, SeniorityLevel
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.ingestion.job_source import JobSource, RawJobPosting
from app.main import app
from app.repositories.candidate_repository import CandidateRepository
from app.services.discovery_service import DiscoveryService


class _FakeAdzuna(JobSource):
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
        llm_provider=fake_provider, source_builders=[lambda profile: _FakeAdzuna(postings)]
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
        assert len(feed) == 1
        opportunity = feed[0]
        assert opportunity["title"] == "Junior Backend Engineer"
        assert opportunity["status"] == "analysed"
        assert opportunity["overall_score"] is not None
        assert opportunity["priority"] is not None
        assert "Python" in opportunity["strong_matches"]
        assert len(opportunity["why_summary"]) > 0

        # Rejected jobs are visible when explicitly requested.
        full_feed_resp = client.get("/api/discovery/opportunities?include_rejected=true")
        assert full_feed_resp.status_code == 200
        assert len(full_feed_resp.json()) == 2
        rejected = next(
            o for o in full_feed_resp.json() if o["status"] == "prefilter_rejected"
        )
        assert rejected["prefilter_reason"] is not None
    finally:
        app.dependency_overrides.clear()


def test_dependency_override_isolation():
    """Sanity check that dependency_overrides is actually cleared between
    tests (guards against the previous test leaking state)."""
    assert get_db not in app.dependency_overrides
    assert get_llm_provider not in app.dependency_overrides
    assert get_discovery_service not in app.dependency_overrides
