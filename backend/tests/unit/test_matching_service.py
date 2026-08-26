"""Unit tests for MatchingService - specifically the anti-hallucination
enforcement: the model may only cite evidence it was actually given, and
`is_gap` is always derived in code, never trusted from the model.
"""

import uuid

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.matching import LLMMatchingOutput, LLMRequirementMatchItem
from app.domain.candidate import Candidate, Evidence
from app.domain.enums import (
    AIOperationType,
    EvidenceTier,
    RequirementCategory,
    RequirementImportance,
)
from app.domain.job import ExtractedRequirement
from app.services.matching_service import MatchingService

REAL_EVIDENCE_ID = uuid.uuid4()
FABRICATED_EVIDENCE_ID = str(uuid.uuid4())


def _candidate_with_evidence() -> Candidate:
    return Candidate(
        name="Test Candidate",
        evidence=[
            Evidence(
                id=REAL_EVIDENCE_ID,
                source_type="project",
                source_label="AFL Project",
                statement="Built Python data pipelines",
                skill_tags=["python"],
            )
        ],
    )


def test_fabricated_evidence_id_is_stripped_and_tier_downgraded():
    requirement = ExtractedRequirement(
        name="Python",
        raw_phrase="Python",
        category=RequirementCategory.TECHNICAL_SKILL,
        importance=RequirementImportance.REQUIRED,
    )
    candidate = _candidate_with_evidence()

    provider = FakeLLMProvider()
    provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.95,
                    evidence_ids=[FABRICATED_EVIDENCE_ID],  # not in candidate's evidence set
                    evidence_summary="Directly demonstrated in a project.",
                )
            ]
        ),
    )

    result, _trace = MatchingService(provider).match(
        requirements=[requirement], candidate=candidate, input_identifier="job-1"
    )

    match = result.matches[0]
    assert match.tier == EvidenceTier.NO_EVIDENCE
    assert match.evidence_ids == []
    assert match.is_gap is True


def test_valid_evidence_id_is_kept():
    requirement = ExtractedRequirement(
        name="Python",
        raw_phrase="Python",
        category=RequirementCategory.TECHNICAL_SKILL,
        importance=RequirementImportance.REQUIRED,
    )
    candidate = _candidate_with_evidence()

    provider = FakeLLMProvider()
    provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING,
        LLMMatchingOutput(
            matches=[
                LLMRequirementMatchItem(
                    requirement_name="Python",
                    tier=EvidenceTier.EXPLICIT,
                    confidence=0.95,
                    evidence_ids=[str(REAL_EVIDENCE_ID)],
                    evidence_summary="Directly demonstrated in a project.",
                )
            ]
        ),
    )

    result, _trace = MatchingService(provider).match(
        requirements=[requirement], candidate=candidate, input_identifier="job-1"
    )

    match = result.matches[0]
    assert match.tier == EvidenceTier.EXPLICIT
    assert match.evidence_ids == [REAL_EVIDENCE_ID]
    assert match.is_gap is False


def test_model_is_gap_field_does_not_exist_on_wire_schema():
    """LLMRequirementMatchItem intentionally has no `is_gap` field - it is
    always computed by MatchingService, never taken from the model."""
    assert "is_gap" not in LLMRequirementMatchItem.model_fields


def test_required_requirement_missing_from_model_output_becomes_a_gap():
    requirements = [
        ExtractedRequirement(
            name="Python",
            raw_phrase="Python",
            category=RequirementCategory.TECHNICAL_SKILL,
            importance=RequirementImportance.REQUIRED,
        ),
        ExtractedRequirement(
            name="Rust",
            raw_phrase="Rust",
            category=RequirementCategory.TECHNICAL_SKILL,
            importance=RequirementImportance.REQUIRED,
        ),
    ]
    candidate = _candidate_with_evidence()

    provider = FakeLLMProvider()
    # Model only responds about Python, silently drops Rust.
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

    result, _trace = MatchingService(provider).match(
        requirements=requirements, candidate=candidate, input_identifier="job-1"
    )

    rust_match = next(m for m in result.matches if m.requirement_name == "Rust")
    assert rust_match.tier == EvidenceTier.NO_EVIDENCE
    assert rust_match.is_gap is True


def test_location_and_work_rights_never_call_the_llm():
    """Location/work-rights requirements are matched deterministically
    against candidate preferences - no LLM call should happen at all."""
    requirements = [
        ExtractedRequirement(
            name="Full Australian work rights",
            raw_phrase="Must have full Australian work rights",
            category=RequirementCategory.WORK_RIGHTS,
            importance=RequirementImportance.REQUIRED,
        ),
    ]
    candidate = Candidate(name="Test Candidate")
    candidate.preferences.work_rights = ["Full Australian work rights, no sponsorship required"]

    provider = FakeLLMProvider()  # no canned response registered at all

    result, trace = MatchingService(provider).match(
        requirements=requirements, candidate=candidate, input_identifier="job-1"
    )

    assert trace is None  # LLM was never invoked
    assert result.matches[0].tier == EvidenceTier.EXPLICIT
