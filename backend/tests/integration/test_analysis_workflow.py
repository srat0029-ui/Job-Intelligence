"""End-to-end test of the core V1 workflow through the real API + real
Postgres, with a FakeLLMProvider standing in for Claude so the test suite
never needs network access or an API key.

Covers the V1 success criteria end to end: create profile -> paste job ->
extract -> match -> score -> retrieve analysis.
"""

from fastapi.testclient import TestClient

from app.ai.providers.factory import get_llm_provider
from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.api.deps import get_db
from app.domain.candidate import Candidate, CandidatePreferences, Evidence
from app.domain.enums import AIOperationType, EvidenceTier
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.main import app
from app.repositories.candidate_repository import CandidateRepository


def _seed_candidate(db) -> Candidate:
    candidate = Candidate(
        name="Integration Test Candidate",
        evidence=[
            Evidence(
                source_type="project",
                source_label="AFL Pricing Engine",
                statement="Built a FastAPI backend with SQLAlchemy and Python.",
                skill_tags=["python", "fastapi", "sqlalchemy"],
            )
        ],
        preferences=CandidatePreferences(preferred_locations=["Melbourne"]),
    )
    return CandidateRepository().upsert(db, candidate)


def test_full_analysis_workflow(db):
    saved_candidate = _seed_candidate(db)
    evidence_id = str(saved_candidate.evidence[0].id)

    fake_provider = FakeLLMProvider()
    fake_provider.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            requirements=[
                ExtractedRequirement(
                    name="Python",
                    raw_phrase="3+ years Python",
                    category="technical_skill",
                    importance="required",
                ),
                ExtractedRequirement(
                    name="Kubernetes",
                    raw_phrase="Kubernetes experience a plus",
                    category="technical_skill",
                    importance="preferred",
                ),
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
                    evidence_summary="Directly used in a real backend project.",
                ),
                LLMRequirementMatchItem(
                    requirement_name="Kubernetes",
                    tier=EvidenceTier.NO_EVIDENCE,
                    confidence=0.8,
                    evidence_ids=[],
                    evidence_summary="No evidence of Kubernetes experience on file.",
                ),
            ]
        ),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    try:
        client = TestClient(app)

        create_resp = client.post(
            "/api/jobs",
            json={
                "title": "Backend Engineer",
                "company": "Acme Corp",
                "location": "Melbourne, VIC",
                "raw_description": "Backend engineer with 3+ years Python. Kubernetes a plus.",
            },
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        analyze_resp = client.post(f"/api/jobs/{job_id}/analyze")
        assert analyze_resp.status_code == 200
        analysis = analyze_resp.json()

        assert analysis["extracted_job"]["title"] == "Backend Engineer"
        assert len(analysis["match_result"]["matches"]) == 2
        python_match = next(
            m for m in analysis["match_result"]["matches"] if m["requirement_name"] == "Python"
        )
        assert python_match["tier"] == "explicit"
        assert python_match["evidence_ids"] == [evidence_id]

        assert 0 <= analysis["fit_score"]["overall_score"] <= 100
        assert analysis["fit_score"]["recommendation"] in (
            "strong_apply",
            "apply",
            "stretch",
            "low_priority",
        )

        # Reopening a previously analysed job returns the same persisted analysis.
        fetch_resp = client.get(f"/api/jobs/{job_id}/analysis")
        assert fetch_resp.status_code == 200
        assert fetch_resp.json()["id"] == analysis["id"]
    finally:
        app.dependency_overrides.clear()


def test_analyze_without_candidate_profile_returns_409(db):
    fake_provider = FakeLLMProvider()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    try:
        client = TestClient(app)
        create_resp = client.post(
            "/api/jobs",
            json={"title": "X", "company": "Y", "raw_description": "desc"},
        )
        job_id = create_resp.json()["id"]

        analyze_resp = client.post(f"/api/jobs/{job_id}/analyze")
        assert analyze_resp.status_code == 409
    finally:
        app.dependency_overrides.clear()
