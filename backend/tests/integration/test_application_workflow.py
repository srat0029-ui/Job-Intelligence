"""Full Milestone 4A integration test, through the real HTTP API against a
real Postgres, with FakeLLMProvider/FixtureResearchProvider standing in for
Claude/the network:

    Analysed job -> company research (fixture) -> evidence retrieval
    -> gap analysis -> application strategy -> tailored CV suggestions
    -> cover letter generation -> grounding reviewer
    -> persisted Application Workspace

Verifies the four properties the milestone brief called out explicitly:
1. candidate claims (CV suggestions, cover letter) reference valid candidate
   evidence IDs
2. company claims (strategy, cover letter) reference valid research claim
   IDs
3. an intentionally hallucinated metric in a CV suggestion is rejected
4. the job's final numerical fit score is never changed by anything in
   this workflow
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.ai.providers.factory import get_llm_provider
from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.application_strategy import LLMApplicationStrategyOutput
from app.ai.schemas.company_research import LLMCompanyResearchOutput, LLMResearchClaimItem
from app.ai.schemas.cover_letter import LLMCoverLetterOutput
from app.ai.schemas.cv_tailoring import LLMCVBulletSuggestion, LLMCVTailoringOutput
from app.ai.schemas.gap_strategy import LLMGapStrategyItem, LLMGapStrategyOutput
from app.ai.schemas.grounding_review import LLMGroundingReviewOutput
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.api.deps import get_db, get_research_provider
from app.domain.candidate import Candidate, CandidatePreferences, Evidence, Project
from app.domain.enums import AIOperationType, ClaimVerificationStatus, EvidenceTier, ReviewVerdict
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.ingestion.research_provider import FixtureResearchProvider, RawResearchDocument
from app.main import app
from app.repositories.candidate_repository import CandidateRepository

RESEARCH_URL = "https://acme.example/about"
RESEARCH_TEXT = "Acme Corp builds real-time fraud detection software for banks."
CV_ORIGINAL_BULLET = "Built an AFL analytics platform using Python and React."


def _seed_candidate(db) -> Candidate:
    candidate = Candidate(
        name="Integration Test Candidate",
        projects=[
            Project(
                name="AFL Pricing Engine",
                description=CV_ORIGINAL_BULLET,
                technologies=["Python", "React"],
            )
        ],
        evidence=[
            Evidence(
                source_type="project",
                source_label="AFL Pricing Engine",
                statement="Built a FastAPI backend with SQLAlchemy and Python.",
                skill_tags=["python", "fastapi", "sqlalchemy"],
            ),
            Evidence(
                source_type="project",
                source_label="Docker Deployment",
                statement="Deployed a containerised service with Docker.",
                skill_tags=["docker"],
            ),
        ],
        preferences=CandidatePreferences(preferred_locations=["Melbourne"]),
    )
    return CandidateRepository().upsert(db, candidate)


def test_full_application_intelligence_workflow(db):
    saved_candidate = _seed_candidate(db)
    python_evidence_id = str(saved_candidate.evidence[0].id)
    docker_evidence_id = str(saved_candidate.evidence[1].id)

    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.JOB_EXTRACTION,
        ExtractedJob(
            title="Backend Engineer",
            company="Acme Corp",
            location="Melbourne, VIC",
            requirements=[
                ExtractedRequirement(
                    name="Python", raw_phrase="3+ years Python",
                    category="technical_skill", importance="required",
                ),
                ExtractedRequirement(
                    name="AWS", raw_phrase="Production AWS experience",
                    category="technical_skill", importance="required",
                ),
            ],
        ),
    )
    fake_llm.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python", tier=EvidenceTier.EXPLICIT, confidence=0.9,
                    evidence_ids=[python_evidence_id],
                    evidence_summary="Directly used in a real backend project.",
                ),
                LLMRequirementMatchItem(
                    requirement_name="AWS", tier=EvidenceTier.NO_EVIDENCE, confidence=0.8,
                    evidence_ids=[], evidence_summary="No AWS evidence on file.",
                ),
            ]
        ),
    )
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(
            claims=[
                LLMResearchClaimItem(
                    category="what_company_does",
                    claim="Acme builds fraud detection software for banks.",
                    supporting_excerpt=RESEARCH_TEXT,
                    verification_status=ClaimVerificationStatus.VERIFIED_FACT,
                    confidence=0.9,
                )
            ]
        ),
    )
    fake_llm.set_response(
        AIOperationType.GAP_ANALYSIS,
        LLMGapStrategyOutput(
            items=[
                LLMGapStrategyItem(
                    requirement_name="AWS",
                    strategy_category="demonstrate_transferable",
                    guidance="No direct AWS experience - position Docker deployment as adjacent.",
                    adjacent_evidence_ids=[docker_evidence_id],
                )
            ]
        ),
    )
    fake_llm.set_response(
        AIOperationType.APPLICATION_STRATEGY,
        LLMApplicationStrategyOutput(
            positioning="Strong Python backend experience with adjacent infra exposure.",
            lead_evidence_ids=[python_evidence_id],
            skills_to_emphasise=["Python"],
            skills_to_deemphasise=[],
            likely_concerns=[],
            motivation_themes=["Fraud detection at scale"],
        ),
    )
    fake_llm.set_response(
        AIOperationType.CV_TAILORING,
        LLMCVTailoringOutput(
            suggestions=[
                LLMCVBulletSuggestion(
                    section="project",
                    source_ref_label="AFL Pricing Engine",
                    original_text=CV_ORIGINAL_BULLET,
                    suggested_text="Built a full-stack Python/FastAPI analytics platform "
                    "with SQLAlchemy.",
                    relevance_rank=1,
                    supporting_evidence_ids=[python_evidence_id],
                ),
                LLMCVBulletSuggestion(
                    section="project",
                    source_ref_label="AFL Pricing Engine",
                    original_text=CV_ORIGINAL_BULLET,
                    suggested_text="Built a platform that improved query performance by 63%.",
                    relevance_rank=2,
                    supporting_evidence_ids=[python_evidence_id],
                ),
            ],
            section_emphasis=["projects"],
        ),
    )
    fake_llm.set_response(
        AIOperationType.COVER_LETTER,
        LLMCoverLetterOutput(
            body="I'm excited to apply my Python backend experience to Acme's fraud "
            "detection platform.",
            evidence_ids_used=[python_evidence_id],
            research_claim_ids_used=[],
        ),
    )
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(verdict=ReviewVerdict.PASS_WITH_WARNINGS, issues=[]),
    )

    research_provider = FixtureResearchProvider()
    research_provider.register(
        RESEARCH_URL,
        RawResearchDocument(
            url=RESEARCH_URL, domain="acme.example", title="About Acme",
            text=RESEARCH_TEXT, fetched_at=datetime.now(UTC),
        ),
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_research_provider] = lambda: research_provider
    try:
        client = TestClient(app)

        create_resp = client.post(
            "/api/jobs",
            json={
                "title": "Backend Engineer",
                "company": "Acme Corp",
                "location": "Melbourne, VIC",
                "raw_description": "Backend engineer, 3+ years Python. Production AWS required.",
            },
        )
        job_id = create_resp.json()["id"]

        analyze_resp = client.post(f"/api/jobs/{job_id}/analyze")
        assert analyze_resp.status_code == 200
        original_fit_score = analyze_resp.json()["fit_score"]["overall_score"]

        workspace_resp = client.post(f"/api/jobs/{job_id}/workspace")
        assert workspace_resp.status_code == 200
        workspace_id = workspace_resp.json()["id"]

        research_resp = client.post(
            f"/api/application-workspaces/{workspace_id}/research/sources",
            json={"url": RESEARCH_URL, "source_type": "official_website"},
        )
        assert research_resp.status_code == 200
        bundle_resp = client.get(f"/api/application-workspaces/{workspace_id}/research")
        claims = bundle_resp.json()["claims"]
        assert len(claims) == 1
        research_claim_id = claims[0]["id"]

        strategy_resp = client.post(f"/api/application-workspaces/{workspace_id}/strategy")
        assert strategy_resp.status_code == 200
        strategy = strategy_resp.json()
        # Property 2: company claims reference valid research claim IDs.
        assert set(strategy["source_research_claim_ids"]) == {research_claim_id}
        assert strategy["recommendation"] in ("strong_apply", "apply", "stretch", "low_priority")

        cv_resp = client.post(f"/api/application-workspaces/{workspace_id}/cv-tailoring")
        assert cv_resp.status_code == 200
        cv_batch = cv_resp.json()
        suggestions = cv_batch["suggestions"]
        assert len(suggestions) == 2

        # Property 1: candidate claims reference valid candidate evidence IDs.
        valid_evidence_ids = {python_evidence_id, docker_evidence_id}
        for suggestion in suggestions:
            assert set(suggestion["supporting_evidence_ids"]) <= valid_evidence_ids

        # Property 3: the intentionally hallucinated metric (63%, never
        # mentioned anywhere in the original text or cited evidence) must be
        # rejected by CVTailoringService's grounding check.
        hallucinated = next(s for s in suggestions if "63%" in s["suggested_text"])
        assert hallucinated["passed_grounding_check"] is False
        assert any("invented_metric" in issue for issue in hallucinated["grounding_issues"])
        clean = next(s for s in suggestions if "63%" not in s["suggested_text"])
        assert clean["passed_grounding_check"] is True

        cover_letter_resp = client.post(f"/api/application-workspaces/{workspace_id}/cover-letter")
        assert cover_letter_resp.status_code == 200
        cover_letter = cover_letter_resp.json()
        assert set(cover_letter["source_evidence_ids"]) <= valid_evidence_ids
        assert cover_letter["meta"]["reviewer_result"] in ("pass", "pass_with_warnings", "fail")

        # Property 4: the job's fit score is never touched by any of the above.
        final_analysis_resp = client.get(f"/api/jobs/{job_id}/analysis")
        final_fit_score = final_analysis_resp.json()["fit_score"]["overall_score"]
        assert final_fit_score == original_fit_score

        # The workspace itself is genuinely persisted, not just in-memory.
        overview_resp = client.get(f"/api/application-workspaces/{workspace_id}")
        assert overview_resp.status_code == 200
        overview = overview_resp.json()
        assert overview["has_strategy"] is True
        assert overview["has_cv_tailoring"] is True
        assert overview["has_cover_letter"] is True
        assert overview["overall_score"] == original_fit_score
    finally:
        app.dependency_overrides.clear()
