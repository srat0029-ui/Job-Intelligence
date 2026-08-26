"""Unit tests for the grounding reviewer: PASS/PASS_WITH_WARNINGS/FAIL
paths, and that a code-level structural check (invented metric/technology)
forces FAIL regardless of what the LLM reviewer itself concludes."""

from __future__ import annotations

import uuid

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.grounding_review import LLMGroundingIssue, LLMGroundingReviewOutput
from app.domain.candidate import Evidence
from app.domain.enums import AIOperationType, ReviewVerdict
from app.services.grounding_reviewer_service import GroundingReviewerService


def _evidence() -> Evidence:
    return Evidence(
        id=uuid.uuid4(), source_type="project", source_label="Project",
        statement="Built a Python data pipeline.", skill_tags=["python"],
    )


def test_clean_content_passes():
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(verdict=ReviewVerdict.PASS, issues=[]),
    )
    service = GroundingReviewerService(fake_llm)

    result, trace = service.review(
        content_type="cover_letter", generated_text="I built a Python data pipeline.",
        job_title="Engineer", company="Acme", evidence=[_evidence()], research_claims=[],
        input_identifier="test",
    )
    assert result.verdict == ReviewVerdict.PASS
    assert trace is not None


def test_llm_warning_only_yields_pass_with_warnings():
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(
            verdict=ReviewVerdict.PASS_WITH_WARNINGS,
            issues=[
                LLMGroundingIssue(
                    category="writing_quality", severity="warning", description="A bit generic."
                )
            ],
        ),
    )
    service = GroundingReviewerService(fake_llm)

    result, _trace = service.review(
        content_type="cover_letter", generated_text="I built a Python data pipeline.",
        job_title="Engineer", company="Acme", evidence=[_evidence()], research_claims=[],
        input_identifier="test",
    )
    assert result.verdict == ReviewVerdict.PASS_WITH_WARNINGS
    assert len(result.issues) == 1


def test_code_level_invented_metric_forces_fail_even_if_llm_says_pass():
    """The LLM reviewer itself says PASS, but the text contains a number
    nowhere in the grounded evidence - code must override to FAIL."""
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(verdict=ReviewVerdict.PASS, issues=[]),
    )
    service = GroundingReviewerService(fake_llm)

    result, _trace = service.review(
        content_type="cover_letter",
        generated_text="I reduced processing time by 73% using Python.",
        job_title="Engineer", company="Acme", evidence=[_evidence()], research_claims=[],
        input_identifier="test",
    )
    assert result.verdict == ReviewVerdict.FAIL
    assert any(i.severity == "fail" for i in result.issues)


def test_llm_fail_severity_yields_fail_verdict():
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.GROUNDING_REVIEW,
        LLMGroundingReviewOutput(
            verdict=ReviewVerdict.FAIL,
            issues=[
                LLMGroundingIssue(
                    category="candidate_grounding", severity="fail",
                    description="Overstates transferable experience as direct experience.",
                )
            ],
        ),
    )
    service = GroundingReviewerService(fake_llm)

    result, _trace = service.review(
        content_type="cover_letter", generated_text="I have direct AWS production experience.",
        job_title="Engineer", company="Acme", evidence=[_evidence()], research_claims=[],
        input_identifier="test",
    )
    assert result.verdict == ReviewVerdict.FAIL
