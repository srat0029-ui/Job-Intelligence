"""Unit tests for gap-analysis coverage classification (deterministic) and
per-gap strategy generation (LLM, whitelist-enforced, only called when a
genuine gap exists)."""

from __future__ import annotations

import uuid

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.gap_strategy import LLMGapStrategyItem, LLMGapStrategyOutput
from app.domain.candidate import Evidence
from app.domain.enums import (
    AIOperationType,
    EvidenceStrength,
    EvidenceTier,
    GapStrategyCategory,
    RequirementCategory,
)
from app.domain.matching import MatchResult, RequirementMatch
from app.services.gap_analysis_service import GapAnalysisService, classify_coverage


def _match(name, tier, is_gap, importance="required"):
    return RequirementMatch(
        requirement_name=name, category=RequirementCategory.TECHNICAL_SKILL,
        importance=importance, tier=tier, confidence=0.8, is_gap=is_gap,
    )


def test_classify_coverage_maps_tiers_to_evidence_strength():
    match_result = MatchResult(
        matches=[
            _match("Python", EvidenceTier.EXPLICIT, is_gap=False),
            _match("Docker", EvidenceTier.TRANSFERABLE, is_gap=False),
            _match("Kubernetes", EvidenceTier.WEAK_INFERENCE, is_gap=False, importance="preferred"),
            _match("AWS", EvidenceTier.NO_EVIDENCE, is_gap=True),
        ]
    )
    coverage = classify_coverage(match_result)
    strengths = {c.requirement_name: c.strength for c in coverage}
    assert strengths["Python"] == EvidenceStrength.STRONG
    assert strengths["Docker"] == EvidenceStrength.PARTIAL
    assert strengths["Kubernetes"] == EvidenceStrength.WEAK
    assert strengths["AWS"] == EvidenceStrength.GAP


def test_no_gaps_means_no_llm_call():
    match_result = MatchResult(matches=[_match("Python", EvidenceTier.EXPLICIT, is_gap=False)])
    fake_llm = FakeLLMProvider()  # no response registered - would raise if called
    service = GapAnalysisService(fake_llm)

    coverage, strategies, trace = service.analyze(
        match_result=match_result, evidence=[], input_identifier="test"
    )
    assert strategies == []
    assert trace is None


def test_genuine_gap_gets_llm_strategy_with_whitelisted_evidence():
    docker_evidence = Evidence(
        id=uuid.uuid4(), source_type="project", source_label="Docker project",
        statement="Deployed a containerised service with Docker.", skill_tags=["docker"],
    )
    match_result = MatchResult(matches=[_match("AWS", EvidenceTier.NO_EVIDENCE, is_gap=True)])
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.GAP_ANALYSIS,
        LLMGapStrategyOutput(
            items=[
                LLMGapStrategyItem(
                    requirement_name="AWS",
                    strategy_category=GapStrategyCategory.DEMONSTRATE_TRANSFERABLE,
                    guidance=(
                        "No direct AWS experience - position container deployment as adjacent."
                    ),
                    adjacent_evidence_ids=[str(docker_evidence.id), "not-a-real-id"],
                )
            ]
        ),
    )
    service = GapAnalysisService(fake_llm)

    coverage, strategies, trace = service.analyze(
        match_result=match_result, evidence=[docker_evidence], input_identifier="test"
    )
    assert trace is not None
    assert len(strategies) == 1
    assert strategies[0].strategy_category == GapStrategyCategory.DEMONSTRATE_TRANSFERABLE
    # the bogus id must be stripped, never trusted
    assert strategies[0].adjacent_evidence_ids == [docker_evidence.id]


def test_gap_silently_dropped_by_model_gets_safe_default():
    match_result = MatchResult(
        matches=[
            _match("AWS", EvidenceTier.NO_EVIDENCE, is_gap=True),
            _match("GCP", EvidenceTier.NO_EVIDENCE, is_gap=True),
        ]
    )
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.GAP_ANALYSIS,
        LLMGapStrategyOutput(
            items=[
                LLMGapStrategyItem(
                    requirement_name="AWS",
                    strategy_category=GapStrategyCategory.ACKNOWLEDGE_HONESTLY,
                    guidance="No AWS experience.",
                )
            ]
        ),
    )
    service = GapAnalysisService(fake_llm)
    _coverage, strategies, _trace = service.analyze(
        match_result=match_result, evidence=[], input_identifier="test"
    )
    assert {s.requirement_name for s in strategies} == {"AWS", "GCP"}
    gcp_strategy = next(s for s in strategies if s.requirement_name == "GCP")
    assert gcp_strategy.strategy_category == GapStrategyCategory.ACKNOWLEDGE_HONESTLY
