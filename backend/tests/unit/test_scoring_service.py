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
    SeniorityLevel,
)
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult, RequirementMatch
from app.services.scoring_service import ScoringService, candidate_seniority_ceiling

REQUIRED = RequirementImportance.REQUIRED
PREFERRED = RequirementImportance.PREFERRED


def _candidate(**prefs_overrides) -> Candidate:
    prefs_overrides.setdefault(
        "preferred_job_categories", ["Graduate Software Engineer", "Junior Software Engineer"]
    )
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


def _extracted_job(
    location: str | None = "Melbourne",
    requirements=None,
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN,
) -> ExtractedJob:
    return ExtractedJob(
        title="Backend Engineer",
        company="Acme",
        location=location,
        requirements=requirements or [],
        seniority=seniority,
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


def test_candidate_seniority_ceiling_derived_from_preferred_categories():
    grad = _candidate(preferred_job_categories=["Graduate Data Scientist"])
    junior = _candidate(preferred_job_categories=["Junior Data Scientist", "Associate Analyst"])
    senior = _candidate(preferred_job_categories=["Senior Data Scientist"])
    none_stated = _candidate(preferred_job_categories=[])

    assert candidate_seniority_ceiling(grad) == SeniorityLevel.GRADUATE
    assert candidate_seniority_ceiling(junior) == SeniorityLevel.JUNIOR
    assert candidate_seniority_ceiling(senior) == SeniorityLevel.SENIOR
    # No seniority word anywhere in stored preferences - falls back to
    # JUNIOR rather than guessing higher or lower.
    assert candidate_seniority_ceiling(none_stated) == SeniorityLevel.JUNIOR


def test_career_stage_fit_rewards_role_at_or_below_candidate_ceiling():
    matches = [
        _match("Python", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
    ]
    candidate = _candidate(preferred_job_categories=["Junior Software Engineer"])
    job = _extracted_job(seniority=SeniorityLevel.GRADUATE)

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.career_stage_fit is not None
    assert score.career_stage_fit.raw_score == 100.0


def test_career_stage_fit_is_none_when_seniority_unknown():
    matches = [
        _match("Python", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
    ]
    candidate = _candidate()
    job = _extracted_job()  # seniority defaults to UNKNOWN

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.career_stage_fit is None


def test_lead_level_role_is_capped_well_below_strong_apply():
    """The AI/ML Security Architect-style case: strong skill overlap but
    clearly senior/lead-level, which must not average out to Strong Apply."""
    matches = [
        _match(f"Skill{i}", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT)
        for i in range(4)
    ]
    candidate = _candidate(preferred_job_categories=["Junior Software Engineer"])
    job = _extracted_job(seniority=SeniorityLevel.LEAD)

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.overall_score <= 35.0
    assert score.recommendation in (Recommendation.STRETCH, Recommendation.LOW_PRIORITY)
    assert score.career_stage_fit is not None
    assert score.career_stage_fit.raw_score <= 10.0


def test_senior_level_role_is_capped_below_strong_apply():
    matches = [
        _match(f"Skill{i}", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT)
        for i in range(4)
    ]
    candidate = _candidate(preferred_job_categories=["Junior Software Engineer"])
    job = _extracted_job(seniority=SeniorityLevel.SENIOR)

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.overall_score <= 60.0
    assert score.recommendation != Recommendation.STRONG_APPLY


def test_graduate_level_role_is_not_penalised_by_career_stage():
    matches = [
        _match(f"Skill{i}", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT)
        for i in range(4)
    ]
    candidate = _candidate(
        preferred_job_categories=["Junior Software Engineer"], preferred_locations=["Melbourne"]
    )
    job = _extracted_job(location="Melbourne, VIC", seniority=SeniorityLevel.GRADUATE)

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.overall_score >= 80.0
    assert score.recommendation == Recommendation.STRONG_APPLY


def test_zero_extracted_requirements_caps_score_at_stretch_tier():
    """Section 4/5 of the review: a job with NO extractable description
    content must not default to a big confident number just because
    location/work-rights happened to look fine (the actual root cause of
    the "everything is exactly 90" saturation bug)."""
    candidate = _candidate(preferred_locations=["Melbourne"])
    job = _extracted_job(location="Melbourne, VIC")

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=[]), candidate=candidate
    )

    assert score.overall_score <= 50.0
    assert score.recommendation != Recommendation.STRONG_APPLY
    assert score.recommendation != Recommendation.APPLY


def test_hard_gap_caps_recommendation_even_when_raw_score_would_be_very_high():
    """The original `_recommendation` only capped when overall was already
    below STRONG_APPLY_THRESHOLD, so a hard gap on a job that otherwise
    scored well wasn't actually capped at all - fixed so a missing required
    item always caps the recommendation, regardless of how high everything
    else scores."""
    matches = [
        _match(f"Skill{i}", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT)
        for i in range(5)
    ] + [
        _match(
            "AWS Certification", RequirementCategory.EDUCATION, REQUIRED, EvidenceTier.NO_EVIDENCE
        )
    ]
    candidate = _candidate(preferred_locations=["Melbourne"])
    job = _extracted_job(location="Melbourne, VIC")

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.recommendation != Recommendation.STRONG_APPLY
    assert score.overall_score < 80.0


def test_majority_transferable_evidence_caps_below_strong_apply():
    matches = [
        _match("R", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.TRANSFERABLE),
        _match(
            "Statistics", RequirementCategory.DOMAIN_KNOWLEDGE, REQUIRED, EvidenceTier.TRANSFERABLE
        ),
        _match("SQL", RequirementCategory.TECHNICAL_SKILL, REQUIRED, EvidenceTier.EXPLICIT),
    ]
    candidate = _candidate(preferred_locations=["Melbourne"])
    job = _extracted_job(location="Melbourne, VIC")

    score = ScoringService().score(
        extracted_job=job, match_result=MatchResult(matches=matches), candidate=candidate
    )

    assert score.overall_score < 80.0
    assert score.recommendation != Recommendation.STRONG_APPLY


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
