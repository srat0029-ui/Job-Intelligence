"""CI-runnable eval answering "how often does matching incorrectly claim I
have experience?" for a batch of adversarial model responses.

Unlike eval_extraction.py, this needs no API key and no network - it drives
MatchingService with a FakeLLMProvider configured to behave like a model
that (deliberately, for the test) tries to claim evidence it wasn't given,
and asserts the structural guardrail in MatchingService brings the
hallucination rate to exactly zero every time. This is what "the
architecture should exist from V1" means for this metric: a real, repeatable
measurement, not just a promise in a docstring.
"""

from __future__ import annotations

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

REAL_ID = uuid.uuid4()


def _candidate() -> Candidate:
    return Candidate(
        name="Eval Candidate",
        evidence=[
            Evidence(
                id=REAL_ID,
                source_type="project",
                source_label="Project",
                statement="Built things in Python",
                skill_tags=["python"],
            )
        ],
    )


def _requirement(name: str) -> ExtractedRequirement:
    return ExtractedRequirement(
        name=name,
        raw_phrase=name,
        category=RequirementCategory.TECHNICAL_SKILL,
        importance=RequirementImportance.REQUIRED,
    )


# Each scenario simulates one adversarial/careless model response.
ADVERSARIAL_SCENARIOS = [
    # Cites a fabricated evidence id outright.
    LLMRequirementMatchItem(
        requirement_name="Rust",
        tier=EvidenceTier.EXPLICIT,
        confidence=0.99,
        evidence_ids=[str(uuid.uuid4())],
        evidence_summary="Extensive Rust experience.",
    ),
    # Claims explicit tier but provides zero evidence.
    LLMRequirementMatchItem(
        requirement_name="Kubernetes",
        tier=EvidenceTier.EXPLICIT,
        confidence=0.9,
        evidence_ids=[],
        evidence_summary="Definitely used Kubernetes.",
    ),
    # Mixes one real id with one fabricated id.
    LLMRequirementMatchItem(
        requirement_name="Go",
        tier=EvidenceTier.EXPLICIT,
        confidence=0.85,
        evidence_ids=[str(REAL_ID), str(uuid.uuid4())],
        evidence_summary="Used Go extensively.",
    ),
]


def test_hallucination_rate_is_zero_across_adversarial_scenarios():
    candidate = _candidate()
    requirements = [_requirement(item.requirement_name) for item in ADVERSARIAL_SCENARIOS]

    provider = FakeLLMProvider()
    provider.set_response(
        AIOperationType.REQUIREMENT_MATCHING, LLMMatchingOutput(matches=ADVERSARIAL_SCENARIOS)
    )

    result, _trace = MatchingService(provider).match(
        requirements=requirements, candidate=candidate, input_identifier="eval"
    )

    allowed_ids = {REAL_ID}
    hallucinated = [
        m for m in result.matches if any(eid not in allowed_ids for eid in m.evidence_ids)
    ]
    unsupported_explicit_claims = [
        m for m in result.matches if m.tier == EvidenceTier.EXPLICIT and not m.evidence_ids
    ]

    hallucination_rate = len(hallucinated) / len(result.matches)
    unsupported_rate = len(unsupported_explicit_claims) / len(result.matches)

    print(
        f"hallucination_rate={hallucination_rate:.2f} "
        f"unsupported_explicit_rate={unsupported_rate:.2f}"
    )

    assert hallucination_rate == 0.0
    assert unsupported_rate == 0.0
    # The one scenario with a genuinely valid evidence id should still be honoured.
    go_match = next(m for m in result.matches if m.requirement_name == "Go")
    assert go_match.evidence_ids == [REAL_ID]
