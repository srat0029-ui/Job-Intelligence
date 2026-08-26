"""Unit tests for the deterministic pre-LLM analysis-priority score.

This score decides which eligible postings get expensive AI analysis
FIRST - it must never be confused with (or feed into) the final candidate
fit score, which stays 100% evidence-grounded and LLM-classified-but-
code-scored, per ScoringService.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.discovery import SearchProfile
from app.domain.enums import ATSType, CompanyPriority, JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.services.analysis_priority_service import compute_analysis_priority


def _posting(**overrides) -> RawJobPosting:
    defaults: dict = {
        "title": "Data Analyst",
        "company": "Acme",
        "location": "Melbourne",
        "source_type": JobSourceType.ADZUNA,
        "raw_description": "A generic job description.",
    }
    defaults.update(overrides)
    return RawJobPosting(**defaults)


def _profile(**overrides) -> SearchProfile:
    defaults: dict = {"name": "Test Profile", "locations": ["Melbourne"]}
    defaults.update(overrides)
    return SearchProfile(**defaults)


def test_early_career_title_scores_higher_than_generic():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    generic = compute_analysis_priority(
        posting=_posting(title="Data Analyst"), search_profile=_profile(), now=now
    )
    graduate = compute_analysis_priority(
        posting=_posting(title="Graduate Data Analyst"), search_profile=_profile(), now=now
    )
    assert graduate > generic


def test_senior_title_scores_lower_than_generic():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    generic = compute_analysis_priority(
        posting=_posting(title="Data Analyst"), search_profile=_profile(), now=now
    )
    senior = compute_analysis_priority(
        posting=_posting(title="Senior Data Analyst"), search_profile=_profile(), now=now
    )
    assert senior < generic


def test_excessive_years_experience_lowers_priority():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    baseline = compute_analysis_priority(
        posting=_posting(raw_description="A great role."), search_profile=_profile(), now=now
    )
    demanding = compute_analysis_priority(
        posting=_posting(raw_description="Requires 10+ years of experience."),
        search_profile=_profile(),
        now=now,
    )
    assert demanding < baseline


def test_preferred_location_boosts_priority():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    profile = _profile(locations=["Melbourne"], location_priority={"Melbourne": 1})
    matched = compute_analysis_priority(
        posting=_posting(location="Melbourne, VIC"), search_profile=profile, now=now
    )
    unmatched = compute_analysis_priority(
        posting=_posting(location="Perth, WA"), search_profile=profile, now=now
    )
    assert matched > unmatched


def test_recent_posting_scores_higher_than_stale():
    now = datetime(2026, 1, 31, tzinfo=UTC)
    recent = compute_analysis_priority(
        posting=_posting(published_at=now - timedelta(days=1)),
        search_profile=_profile(),
        now=now,
    )
    stale = compute_analysis_priority(
        posting=_posting(published_at=now - timedelta(days=60)),
        search_profile=_profile(),
        now=now,
    )
    assert recent > stale


def test_direct_ats_source_scores_higher_than_aggregator():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    adzuna = compute_analysis_priority(
        posting=_posting(source_type=JobSourceType.ADZUNA), search_profile=_profile(), now=now
    )
    lever = compute_analysis_priority(
        posting=_posting(source_type=JobSourceType.LEVER), search_profile=_profile(), now=now
    )
    assert lever > adzuna


def test_high_priority_company_boosts_but_low_priority_penalises():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    posting = _posting()
    profile = _profile()

    high = compute_analysis_priority(
        posting=posting,
        search_profile=profile,
        watchlist_entry=CompanyWatchlistEntry(
            company_name="Acme",
            ats_type=ATSType.LEVER,
            ats_identifier="acme",
            priority=CompanyPriority.HIGH,
        ),
        now=now,
    )
    normal = compute_analysis_priority(
        posting=posting, search_profile=profile, watchlist_entry=None, now=now
    )
    low = compute_analysis_priority(
        posting=posting,
        search_profile=profile,
        watchlist_entry=CompanyWatchlistEntry(
            company_name="Acme",
            ats_type=ATSType.LEVER,
            ats_identifier="acme",
            priority=CompanyPriority.LOW,
        ),
        now=now,
    )
    assert high > normal > low


def test_score_is_clamped_between_0_and_100():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    extreme_negative = compute_analysis_priority(
        posting=_posting(
            title="Senior Principal Lead Director",
            raw_description="Requires 20+ years of experience.",
            published_at=now - timedelta(days=365),
        ),
        search_profile=_profile(),
        watchlist_entry=CompanyWatchlistEntry(
            company_name="Acme",
            ats_type=ATSType.LEVER,
            ats_identifier="acme",
            priority=CompanyPriority.LOW,
        ),
        now=now,
    )
    assert 0.0 <= extreme_negative <= 100.0
