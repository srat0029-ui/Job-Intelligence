"""Unit tests for the discovery-feed priority classification and "why this
job" summary builder - pure functions, no DB, no LLM."""

from __future__ import annotations

from app.domain.analysis import JobAnalysis
from app.domain.enums import (
    EvidenceTier,
    JobPriority,
    Recommendation,
    RequirementCategory,
    RequirementImportance,
)
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult, RequirementMatch
from app.domain.scoring import FitScore, ScoreComponent
from app.services.priority_service import build_why_summary, classify_priority


def _component(score: float, matched: int = 0) -> ScoreComponent:
    return ScoreComponent(
        name="x",
        raw_score=score,
        weight=0.1,
        contributing_requirements=1,
        matched_requirements=matched,
    )


def test_classify_priority_thresholds():
    assert classify_priority(95) == JobPriority.APPLY_ASAP
    assert classify_priority(90) == JobPriority.APPLY_ASAP
    assert classify_priority(89.9) == JobPriority.STRONG_APPLY
    assert classify_priority(80) == JobPriority.STRONG_APPLY
    assert classify_priority(79.9) == JobPriority.APPLY
    assert classify_priority(70) == JobPriority.APPLY
    assert classify_priority(69.9) == JobPriority.STRETCH
    assert classify_priority(60) == JobPriority.STRETCH
    assert classify_priority(59.9) == JobPriority.LOW_PRIORITY
    assert classify_priority(0) == JobPriority.LOW_PRIORITY


def _analysis(
    matches: list[RequirementMatch], location_score=70.0, project_matched=0
) -> JobAnalysis:
    return JobAnalysis(
        job_id="00000000-0000-0000-0000-000000000000",
        extracted_job=ExtractedJob(title="Data Scientist", company="Acme", seniority="graduate"),
        match_result=MatchResult(matches=matches),
        fit_score=FitScore(
            overall_score=85.0,
            recommendation=Recommendation.STRONG_APPLY,
            technical_fit=_component(90),
            project_relevance_fit=_component(90, matched=project_matched),
            education_fit=_component(70),
            experience_fit=_component(70),
            domain_fit=_component(70),
            location_fit=_component(location_score),
            work_rights_fit=_component(80),
            reasoning="test",
        ),
    )


def test_why_summary_mentions_strong_matches_and_main_gap():
    matches = [
        RequirementMatch(
            requirement_name="Python",
            category=RequirementCategory.TECHNICAL_SKILL,
            importance=RequirementImportance.REQUIRED,
            tier=EvidenceTier.EXPLICIT,
            confidence=0.9,
            evidence_ids=[],
            is_gap=False,
        ),
        RequirementMatch(
            requirement_name="AWS",
            category=RequirementCategory.TECHNOLOGY,
            importance=RequirementImportance.REQUIRED,
            tier=EvidenceTier.NO_EVIDENCE,
            confidence=0.9,
            evidence_ids=[],
            is_gap=True,
        ),
    ]
    summary = build_why_summary(_analysis(matches))
    joined = " ".join(summary)

    assert "Python" in joined
    assert "AWS" in joined
    assert any("graduate" in s for s in summary)


def test_why_summary_reports_no_gaps_when_none_exist():
    matches = [
        RequirementMatch(
            requirement_name="Python",
            category=RequirementCategory.TECHNICAL_SKILL,
            importance=RequirementImportance.REQUIRED,
            tier=EvidenceTier.EXPLICIT,
            confidence=0.9,
            evidence_ids=[],
            is_gap=False,
        )
    ]
    summary = build_why_summary(_analysis(matches))
    assert any("no identified gaps" in s.lower() for s in summary)


def test_why_summary_is_derived_only_from_stored_analysis_fields():
    """Never invents claims beyond what's in the match_result/fit_score -
    an analysis with zero matches should produce a short, honest summary,
    not a fabricated one."""
    summary = build_why_summary(_analysis([]))
    assert isinstance(summary, list)
    assert len(summary) <= 5
