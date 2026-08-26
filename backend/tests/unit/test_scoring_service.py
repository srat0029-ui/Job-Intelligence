"""Unit tests for the deterministic scoring engine.

These are pure-function tests (no DB, no LLM) - the whole point of keeping
scoring deterministic is that its behaviour is fully pinned down by these
tests, and any change to the weighting/threshold constants shows up here
immediately.
"""

from app.domain.candidate import Candidate, CandidatePreferences, Evidence
from app.domain.enums import (
    EvidenceSourceType,
    EvidenceTier,
    Recommendation,
    RequirementCategory,
    RequirementImportance,
)
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult, RequirementMatch
from app.services.scoring_service import ScoringService

REQUIRED = RequirementImportance.REQUIRED
PREFERRED = RequirementImportance.PREFERRED


def _candidate(**prefs_overrides) -> Candidate:
    return Candidate(
        name="Test Candidate",
        evidence=[
            Evidence(
                id=None,
                source_type=EvidenceSourceType.PROJECT.value,
                source_label="Some Project",
                statement="Built things in Python",
                skill_tags=["python"],
            )
        ],
        preferences=CandidatePreferences(**prefs_overrides),
    )


def _extracted_job(location: str | None = "Melbourne", requirements=None) -> ExtractedJob:
    return ExtractedJob(
        title="Backend Engineer",
        company="Acme",
        location=location,
        requirements=requirements or [],
    )


def _match(name, category, importance, tier, is_gap=None) -> RequirementMatch:
    return RequirementMatch(
        requirement_name=name,
        category=category,
        importance=importance,
        tier=tier,
        confidence=0.9,
        evidence_ids=[],
        evidence_summary="test",
        is_gap=is_gap if is_gap is not None else tier == EvidenceTier.NO_EVIDENCE,
    )


def test_all_explicit_matches_yields_strong_apply():
    matches = [
        _match("Python", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
        _match("SQL", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
    ]
    candidate = _candidate(preferred_locations=["Melbourne"])
    job = _extracted_job(location="Melbourne, VIC")

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.overall_score >= 80
    assert score.recommendation == Recommendation.STRONG_APPLY
    assert score.technical_fit.raw_score == 100.0


def test_missing_required_skill_caps_recommendation_even_with_high_score():
    matches = [
        _match("Python", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
        _match(
            "Kubernetes", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.NO_EVIDENCE
        ),
    ]
    candidate = _candidate()
    job = _extracted_job()

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    # Technical fit itself averages to 50 (100 + 0)/2, but even if it didn't,
    # a hard gap on a required skill should never be masked as STRONG_APPLY.
    assert score.recommendation != Recommendation.STRONG_APPLY


def test_category_with_no_requirements_is_excluded_not_defaulted_to_zero():
    matches = [
        _match("Python", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
    ]
    candidate = _candidate()
    job = _extracted_job()  # no education/experience/domain requirements at all

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    # No education requirements were extracted -> education_fit must not be
    # scored as if the candidate failed an education check that never
    # happened.
    assert score.education_fit.contributing_requirements == 0
    assert score.education_fit.raw_score == 70.0  # neutral fallback, not 0
    assert score.overall_score >= 90  # driven almost entirely by the perfect technical match


def test_preferred_gap_is_softer_than_required_gap():
    """A missing PREFERRED item should hurt the technical_fit average less
    than a missing REQUIRED item (lower importance weight in the average),
    and - separately - only a missing REQUIRED item can cap the
    recommendation below STRONG_APPLY (see test above)."""
    base_matches = [
        _match(f"Skill{i}", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT)
        for i in range(3)
    ]
    with_required_gap = base_matches + [
        _match(
            "Kubernetes", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.NO_EVIDENCE
        )
    ]
    with_preferred_gap = base_matches + [
        _match(
            "Kubernetes", RequirementCategory.TECHNICAL_SKILL, PREFERRED, EvidenceTier.NO_EVIDENCE
        )
    ]
    candidate = _candidate()
    job = _extracted_job()

    required_gap_score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=with_required_gap), candidate=candidate
    )
    preferred_gap_score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=with_preferred_gap), candidate=candidate
    )

    assert preferred_gap_score.technical_fit.raw_score > required_gap_score.technical_fit.raw_score
    assert preferred_gap_score.overall_score > required_gap_score.overall_score


def test_location_mismatch_lowers_location_fit():
    candidate = _candidate(preferred_locations=["Sydney"])
    job_far = _extracted_job(location="Perth, WA")
    job_match = _extracted_job(location="Sydney, NSW")

    far_score = ScoringService().score(
        extracted_job=job_far, match_result=MatchResult(matches=[]), candidate=candidate
    )
    match_score = ScoringService().score(
        extracted_job=job_match, match_result=MatchResult(matches=[]), candidate=candidate
    )

    assert match_score.location_fit.raw_score > far_score.location_fit.raw_score


def test_score_is_deterministic_across_runs():
    """Re-running the same inputs must produce byte-identical scores - this
    is the "score stability" property the eval framework checks at a higher
    level (see tests/evals)."""
    matches = [
        _match("Python", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
        _match("Docker", RequirementCategory.TECHNOLOGY, PREFERRED, EvidenceTier.TRANSFERABLE),
    ]
    candidate = _candidate()
    job = _extracted_job()

    scores = [
        ScoringService().score(
            extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
        )
        for _ in range(5)
    ]

    assert len({s.overall_score for s in scores}) == 1
