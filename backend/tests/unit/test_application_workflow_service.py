"""Unit tests for the ApplicationWorkflowService orchestrator: failure
isolation (clear errors for missing workspace/unanalysed job), bounded
regeneration on a persistent grounding FAIL, and generation version history
across repeated strategy generation."""

from __future__ import annotations

import uuid

import pytest

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.application_strategy import LLMApplicationStrategyOutput
from app.ai.schemas.cover_letter import LLMCoverLetterOutput
from app.ai.schemas.cv_tailoring import LLMCVBulletSuggestion, LLMCVTailoringOutput
from app.ai.schemas.grounding_review import LLMGroundingIssue, LLMGroundingReviewOutput
from app.domain.candidate import Candidate, Evidence
from app.domain.enums import (
    AIOperationType,
    CVSection,
    EmploymentType,
    EvidenceTier,
    GenerationStatus,
    JobSourceType,
    RequirementCategory,
    RequirementImportance,
    ReviewVerdict,
    SeniorityLevel,
)
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.domain.matching import MatchResult, RequirementMatch
from app.domain.scoring import FitScore, ScoreComponent
from app.ingestion.job_source import RawJobPosting
from app.ingestion.research_provider import FixtureResearchProvider
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.application_strategy_repository import ApplicationStrategyRepository
from app.repositories.application_workspace_repository import ApplicationWorkspaceRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.job_repository import JobRepository
from app.services.application_workflow_service import (
    ApplicationWorkflowService,
    JobNotAnalysedError,
    WorkspaceNotFoundError,
)


def _component(name: str) -> ScoreComponent:
    return ScoreComponent(
        name=name, raw_score=80.0, weight=0.15, contributing_requirements=1, matched_requirements=1
    )


def _seed_workspace(db) -> tuple[uuid.UUID, Evidence]:
    evidence = Evidence(
        source_type="project", source_label="Data Pipeline Project",
        statement="Built a Python data pipeline with automated tests.", skill_tags=["python"],
    )
    candidate = CandidateRepository().upsert(
        db, Candidate(name="Test Candidate", evidence=[evidence])
    )
    saved_evidence = candidate.evidence[0]

    job = JobRepository().create_from_posting(
        db,
        RawJobPosting(
            title="Backend Engineer", company="Acme", source_type=JobSourceType.MANUAL,
            raw_description="Backend engineer role requiring Python.",
        ),
    )
    extracted_job = ExtractedJob(
        title="Backend Engineer", company="Acme", employment_type=EmploymentType.FULL_TIME,
        seniority=SeniorityLevel.JUNIOR,
        requirements=[
            ExtractedRequirement(
                name="Python", raw_phrase="Python", category=RequirementCategory.TECHNICAL_SKILL,
                importance=RequirementImportance.REQUIRED,
            )
        ],
    )
    match_result = MatchResult(
        matches=[
            RequirementMatch(
                requirement_name="Python", category=RequirementCategory.TECHNICAL_SKILL,
                importance=RequirementImportance.REQUIRED, tier=EvidenceTier.EXPLICIT,
                confidence=0.9, evidence_ids=[saved_evidence.id], is_gap=False,
            )
        ]
    )
    fit_score = FitScore(
        overall_score=80.0, recommendation="apply",
        technical_fit=_component("technical_fit"), project_relevance_fit=_component("project"),
        education_fit=_component("education"), experience_fit=_component("experience"),
        domain_fit=_component("domain"), location_fit=_component("location"),
        work_rights_fit=_component("work_rights"), reasoning="Good match.",
    )
    AnalysisRepository().save(
        db,
        job_id=job.id,
        extracted_job=extracted_job,
        match_result=match_result,
        fit_score=fit_score,
    )

    workspace = ApplicationWorkspaceRepository().get_or_create(db, job.id)
    return workspace.id, saved_evidence


def _strategy_response() -> LLMApplicationStrategyOutput:
    return LLMApplicationStrategyOutput(
        positioning="Strong Python background.",
        lead_evidence_ids=[],
        skills_to_emphasise=["Python"],
        skills_to_deemphasise=[],
        likely_concerns=[],
        motivation_themes=["Learning"],
    )


def test_prepare_strategy_raises_for_unknown_workspace(db):
    fake_llm = FakeLLMProvider()
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())
    with pytest.raises(WorkspaceNotFoundError):
        workflow.prepare_strategy(db, uuid.uuid4())


def test_prepare_strategy_raises_when_job_not_analysed(db):
    job = JobRepository().create_from_posting(
        db,
        RawJobPosting(
            title="Unanalysed Job", company="Acme", source_type=JobSourceType.MANUAL,
            raw_description="desc",
        ),
    )
    workspace = ApplicationWorkspaceRepository().get_or_create(db, job.id)
    fake_llm = FakeLLMProvider()
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())
    with pytest.raises(JobNotAnalysedError):
        workflow.prepare_strategy(db, workspace.id)


def test_prepare_strategy_persists_and_creates_version_1(db):
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(AIOperationType.APPLICATION_STRATEGY, _strategy_response())
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    strategy = workflow.prepare_strategy(db, workspace_id)
    assert strategy.meta.version == 1
    assert strategy.recommendation == "apply"


def test_regenerating_strategy_preserves_prior_version_history(db):
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(AIOperationType.APPLICATION_STRATEGY, _strategy_response())
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    first = workflow.prepare_strategy(db, workspace_id)
    second = workflow.prepare_strategy(db, workspace_id)

    assert first.id != second.id
    assert second.meta.version == first.meta.version + 1

    history = ApplicationStrategyRepository().list_history(db, workspace_id)
    assert len(history) == 2
    archived = next(h for h in history if h.id == first.id)
    assert archived.meta.status == GenerationStatus.ARCHIVED.value


def _cv_tailoring_response() -> LLMCVTailoringOutput:
    return LLMCVTailoringOutput(
        suggestions=[
            LLMCVBulletSuggestion(
                section=CVSection.PROJECT, source_ref_label="none",
                original_text="none", suggested_text="Built a Python data pipeline.",
                relevance_rank=1, supporting_evidence_ids=[],
            )
        ],
        section_emphasis=[],
    )


def test_cv_tailoring_stops_immediately_when_review_passes(db):
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(AIOperationType.CV_TAILORING, _cv_tailoring_response())
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(verdict=ReviewVerdict.PASS, issues=[]),
    )
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    batch = workflow.generate_cv_tailoring(db, workspace_id)
    assert batch.meta.regeneration_attempt == 1
    assert batch.meta.status == GenerationStatus.REVIEWED.value


def test_cv_tailoring_bounded_regeneration_stops_and_marks_needs_review(db):
    """The reviewer always FAILs - the workflow must stop after
    MAX_REGENERATION_ATTEMPTS+1 tries, never loop forever, and surface
    NEEDS_REVIEW rather than silently returning a bad result as if fine."""
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(AIOperationType.CV_TAILORING, _cv_tailoring_response())
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(
            verdict=ReviewVerdict.FAIL,
            issues=[
                LLMGroundingIssue(
                    category="candidate_grounding", severity="fail", description="Always fails."
                )
            ],
        ),
    )
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    batch = workflow.generate_cv_tailoring(db, workspace_id)
    assert batch.meta.status == GenerationStatus.NEEDS_REVIEW.value
    assert batch.meta.reviewer_result == ReviewVerdict.FAIL.value
    # bounded: exactly MAX_REGENERATION_ATTEMPTS + 1 attempts, never unbounded
    from app.services.grounding_reviewer_service import MAX_REGENERATION_ATTEMPTS

    assert batch.meta.regeneration_attempt == MAX_REGENERATION_ATTEMPTS + 1


def _stub_all_generation_responses(fake_llm: FakeLLMProvider) -> None:
    fake_llm.set_response(AIOperationType.APPLICATION_STRATEGY, _strategy_response())
    fake_llm.set_response(AIOperationType.CV_TAILORING, _cv_tailoring_response())
    fake_llm.set_response(
        AIOperationType.COVER_LETTER,
        LLMCoverLetterOutput(body="Dear Hiring Team, ..."),
    )
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(verdict=ReviewVerdict.PASS, issues=[]),
    )


def test_prepare_application_pack_happy_path(db):
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    _stub_all_generation_responses(fake_llm)
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    pack = workflow.prepare_application_pack(db, workspace_id)

    assert pack.job_title == "Backend Engineer"
    assert pack.cover_letter_body == "Dear Hiring Team, ..."
    assert len(pack.cv_suggestions) == 1
    assert pack.brief.why_this_role_fits  # built from the real analysis, non-empty


def test_prepare_application_pack_reuses_existing_generation_by_default(db):
    """Calling prepare twice must not regenerate everything from scratch -
    the second call should reuse the already-persisted strategy/CV/cover
    letter rather than making more (expensive) LLM calls."""
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    _stub_all_generation_responses(fake_llm)
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    first = workflow.prepare_application_pack(db, workspace_id)
    second = workflow.prepare_application_pack(db, workspace_id)

    from app.repositories.application_strategy_repository import ApplicationStrategyRepository
    from app.repositories.cover_letter_repository import CoverLetterRepository
    from app.repositories.cv_tailoring_repository import CVTailoringRepository

    assert len(ApplicationStrategyRepository().list_history(db, workspace_id)) == 1
    assert len(CVTailoringRepository().list_history(db, workspace_id)) == 1
    assert len(CoverLetterRepository().list_history(db, workspace_id)) == 1
    assert first.cover_letter_body == second.cover_letter_body


def test_prepare_application_pack_force_refresh_regenerates_everything(db):
    workspace_id, _evidence = _seed_workspace(db)
    fake_llm = FakeLLMProvider()
    _stub_all_generation_responses(fake_llm)
    workflow = ApplicationWorkflowService(fake_llm, FixtureResearchProvider())

    workflow.prepare_application_pack(db, workspace_id)
    workflow.prepare_application_pack(db, workspace_id, force_refresh=True)

    from app.repositories.application_strategy_repository import ApplicationStrategyRepository

    assert len(ApplicationStrategyRepository().list_history(db, workspace_id)) == 2
