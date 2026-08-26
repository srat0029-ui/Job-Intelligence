"""Unit tests for CV tailoring grounding validation - the concrete checks
that reject invented metrics/technologies rather than trusting the model's
output on its word."""

from __future__ import annotations

import uuid

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.cv_tailoring import LLMCVBulletSuggestion, LLMCVTailoringOutput
from app.domain.candidate import Candidate, Evidence, Project
from app.domain.communication_style import CommunicationStyle
from app.domain.enums import AIOperationType, CVSection
from app.services.cv_tailoring_service import CVTailoringService

ORIGINAL_BULLET = "Built an AFL analytics platform using Python and React."


def _candidate_with_project() -> Candidate:
    return Candidate(
        name="Test",
        projects=[
            Project(
                name="AFL Pricing Engine",
                description=ORIGINAL_BULLET,
                technologies=["Python", "React"],
                highlights=[],
            )
        ],
    )


def _evidence() -> Evidence:
    return Evidence(
        id=uuid.uuid4(), source_type="project", source_label="AFL Pricing Engine",
        statement="Built a FastAPI backend with automated data pipelines.",
        skill_tags=["python", "fastapi"],
    )


def test_valid_suggestion_passes_grounding_check(db):
    candidate = _candidate_with_project()
    evidence = _evidence()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.CV_TAILORING,
        LLMCVTailoringOutput(
            suggestions=[
                LLMCVBulletSuggestion(
                    section=CVSection.PROJECT,
                    source_ref_label="AFL Pricing Engine",
                    original_text=ORIGINAL_BULLET,
                    suggested_text="Built a full-stack Python/FastAPI analytics platform "
                    "with automated data pipelines.",
                    relevance_rank=1,
                    supporting_evidence_ids=[str(evidence.id)],
                )
            ],
            section_emphasis=["projects"],
        ),
    )
    service = CVTailoringService(fake_llm)

    batch, trace = service.generate(
        workspace_id=uuid.uuid4(), job_title="Backend Engineer", company="Acme",
        candidate=candidate, evidence=[evidence], style=CommunicationStyle(),
        input_identifier="test",
    )
    assert trace is not None
    assert len(batch.suggestions) == 1
    assert batch.suggestions[0].passed_grounding_check is True
    assert batch.suggestions[0].grounding_issues == []


def test_invented_metric_is_rejected(db):
    candidate = _candidate_with_project()
    evidence = _evidence()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.CV_TAILORING,
        LLMCVTailoringOutput(
            suggestions=[
                LLMCVBulletSuggestion(
                    section=CVSection.PROJECT,
                    source_ref_label="AFL Pricing Engine",
                    original_text=ORIGINAL_BULLET,
                    suggested_text="Built a platform that reduced processing time by 47% "
                    "using Python and React.",
                    relevance_rank=1,
                    supporting_evidence_ids=[str(evidence.id)],
                )
            ],
            section_emphasis=[],
        ),
    )
    service = CVTailoringService(fake_llm)

    batch, _trace = service.generate(
        workspace_id=uuid.uuid4(), job_title="Backend Engineer", company="Acme",
        candidate=candidate, evidence=[evidence], style=CommunicationStyle(),
        input_identifier="test",
    )
    suggestion = batch.suggestions[0]
    assert suggestion.passed_grounding_check is False
    assert any("invented_metric" in issue for issue in suggestion.grounding_issues)


def test_invented_technology_is_rejected(db):
    candidate = _candidate_with_project()
    evidence = _evidence()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.CV_TAILORING,
        LLMCVTailoringOutput(
            suggestions=[
                LLMCVBulletSuggestion(
                    section=CVSection.PROJECT,
                    source_ref_label="AFL Pricing Engine",
                    original_text=ORIGINAL_BULLET,
                    suggested_text="Built an AFL analytics platform deployed on AWS Kubernetes "
                    "using Python and React.",
                    relevance_rank=1,
                    supporting_evidence_ids=[str(evidence.id)],
                )
            ],
            section_emphasis=[],
        ),
    )
    service = CVTailoringService(fake_llm)

    batch, _trace = service.generate(
        workspace_id=uuid.uuid4(), job_title="Backend Engineer", company="Acme",
        candidate=candidate, evidence=[evidence], style=CommunicationStyle(),
        input_identifier="test",
    )
    suggestion = batch.suggestions[0]
    assert suggestion.passed_grounding_check is False
    assert any("invented_technology" in issue for issue in suggestion.grounding_issues)
    assert any("aws" in issue or "kubernetes" in issue for issue in suggestion.grounding_issues)


def test_evidence_id_outside_offered_set_is_stripped_and_flagged(db):
    candidate = _candidate_with_project()
    evidence = _evidence()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.CV_TAILORING,
        LLMCVTailoringOutput(
            suggestions=[
                LLMCVBulletSuggestion(
                    section=CVSection.PROJECT,
                    source_ref_label="AFL Pricing Engine",
                    original_text=ORIGINAL_BULLET,
                    suggested_text="Built an AFL analytics platform using Python and React.",
                    relevance_rank=1,
                    supporting_evidence_ids=[str(evidence.id), str(uuid.uuid4())],
                )
            ],
            section_emphasis=[],
        ),
    )
    service = CVTailoringService(fake_llm)

    batch, _trace = service.generate(
        workspace_id=uuid.uuid4(), job_title="Backend Engineer", company="Acme",
        candidate=candidate, evidence=[evidence], style=CommunicationStyle(),
        input_identifier="test",
    )
    suggestion = batch.suggestions[0]
    assert suggestion.supporting_evidence_ids == [evidence.id]
    assert suggestion.passed_grounding_check is False
    assert any("offered evidence set" in issue for issue in suggestion.grounding_issues)


def test_original_text_not_in_profile_is_flagged(db):
    candidate = _candidate_with_project()
    evidence = _evidence()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.CV_TAILORING,
        LLMCVTailoringOutput(
            suggestions=[
                LLMCVBulletSuggestion(
                    section=CVSection.PROJECT,
                    source_ref_label="AFL Pricing Engine",
                    original_text="A completely made-up bullet that was never in the profile.",
                    suggested_text="A completely made-up bullet, reworded.",
                    relevance_rank=1,
                    supporting_evidence_ids=[str(evidence.id)],
                )
            ],
            section_emphasis=[],
        ),
    )
    service = CVTailoringService(fake_llm)

    batch, _trace = service.generate(
        workspace_id=uuid.uuid4(), job_title="Backend Engineer", company="Acme",
        candidate=candidate, evidence=[evidence], style=CommunicationStyle(),
        input_identifier="test",
    )
    suggestion = batch.suggestions[0]
    assert suggestion.passed_grounding_check is False
    assert any("does not match any existing" in issue for issue in suggestion.grounding_issues)
