"""Unit tests for the deterministic pre-filter - no LLM, no DB.

Covers both "clearly reject this" and "don't over-reject a stretch role"
per the brief's explicit warning against being too aggressive.
"""

from __future__ import annotations

from app.domain.candidate import Candidate, CandidatePreferences
from app.domain.discovery import SearchProfile
from app.domain.enums import JobSourceType, SeniorityLevel
from app.ingestion.job_source import RawJobPosting
from app.services.prefilter_service import evaluate_prefilter


def _posting(
    title: str, description: str, location: str | None = "Melbourne, VIC"
) -> RawJobPosting:
    return RawJobPosting(
        title=title,
        company="Acme",
        location=location,
        source_type=JobSourceType.ADZUNA,
        raw_description=description,
    )


def _candidate(**prefs) -> Candidate:
    return Candidate(name="Test Candidate", preferences=CandidatePreferences(**prefs))


def _profile(**overrides) -> SearchProfile:
    defaults: dict = {"name": "Test Profile", "locations": ["Melbourne"], "include_remote": True}
    defaults.update(overrides)
    return SearchProfile(**defaults)


def test_senior_title_rejected_for_early_career_profile():
    posting = _posting("Senior Data Scientist", "5 years of experience required.")
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(max_experience_level=SeniorityLevel.GRADUATE),
    )
    assert result.passed is False
    assert "senior" in result.reason.lower()


def test_senior_title_allowed_when_no_experience_ceiling_configured():
    posting = _posting("Senior Data Scientist", "5 years of experience required.")
    result = evaluate_prefilter(
        posting=posting, candidate=_candidate(), search_profile=_profile(max_experience_level=None)
    )
    assert result.passed is True


def test_excessive_years_experience_rejected():
    posting = _posting("Data Scientist", "Must have 10+ years of experience in ML.")
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(max_experience_level=SeniorityLevel.GRADUATE),
    )
    assert result.passed is False
    assert "10" in result.reason


def test_moderate_years_experience_not_rejected_for_mid_ceiling():
    """A stretch-but-reasonable role (6 years) with a MID ceiling should
    survive - the brief explicitly warns against discarding good stretch
    roles."""
    posting = _posting("Data Scientist", "6+ years of experience preferred.")
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(max_experience_level=SeniorityLevel.MID),
    )
    assert result.passed is True


def test_location_mismatch_without_remote_is_rejected():
    posting = _posting("Data Scientist", "Great role.", location="Perth, WA")
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(locations=["Melbourne"], include_remote=False),
    )
    assert result.passed is False
    assert "location" in result.reason.lower()


def test_remote_posting_passes_location_check_when_remote_included():
    posting = _posting("Data Scientist", "This is a fully remote position.", location="Australia")
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(locations=["Melbourne"], include_remote=True),
    )
    assert result.passed is True


def test_no_location_constraint_configured_never_rejects_on_location():
    posting = _posting("Data Scientist", "Great role.", location="Perth, WA")
    result = evaluate_prefilter(
        posting=posting, candidate=_candidate(), search_profile=_profile(locations=[])
    )
    assert result.passed is True


def test_excluded_keyword_rejected():
    posting = _posting("Data Scientist (Sales Focus)", "Great role.")
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(excluded_keywords=["Sales Focus"]),
    )
    assert result.passed is False


def test_work_rights_phrase_rejected_when_candidate_has_no_declared_rights():
    posting = _posting("Data Scientist", "Must have full working rights in Australia.")
    result = evaluate_prefilter(posting=posting, candidate=_candidate(), search_profile=_profile())
    assert result.passed is False
    assert "work rights" in result.reason.lower()


def test_work_rights_phrase_not_rejected_when_candidate_has_declared_rights():
    posting = _posting("Data Scientist", "Must have full working rights in Australia.")
    candidate = _candidate(work_rights=["Australian citizen, full working rights"])
    result = evaluate_prefilter(posting=posting, candidate=candidate, search_profile=_profile())
    assert result.passed is True


def test_ordinary_posting_with_no_red_flags_passes():
    posting = _posting(
        "Graduate Data Analyst",
        "Join our team as a graduate data analyst. 0-2 years experience welcome.",
    )
    result = evaluate_prefilter(
        posting=posting,
        candidate=_candidate(),
        search_profile=_profile(max_experience_level=SeniorityLevel.GRADUATE),
    )
    assert result.passed is True
    assert result.reason is None
