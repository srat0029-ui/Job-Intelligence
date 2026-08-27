"""Deterministic, pre-LLM triage score deciding which eligible postings get
expensive AI analysis FIRST when budget-constrained.

`analysis_priority` is deliberately never called a "fit score" and never
feeds `ScoringService` - it only reorders the `awaiting_analysis` queue
before the per-run/budget caps are applied (see DiscoveryService). Company
preference (CompanyWatchlistEntry.priority) is folded in here specifically
because the brief requires it to affect ANALYSIS ORDER only, never the
final candidate fit score that ScoringService computes after real evidence
matching.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.discovery import SearchProfile
from app.domain.enums import CompanyPriority, JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.services.deduplication_service import normalize_text
from app.services.prefilter_service import SENIOR_TITLE_KEYWORDS, max_years_mentioned

EARLY_CAREER_KEYWORDS = ["graduate", "junior", "associate", "entry level", "early career", "intern"]

# Direct company ATS feeds are already a strong positive signal on their own
# (the user explicitly watchlisted this employer), on top of any company
# priority boost.
DIRECT_SOURCE_TYPES = {JobSourceType.LEVER, JobSourceType.GREENHOUSE}

COMPANY_PRIORITY_BONUS = {
    CompanyPriority.HIGH: 15.0,
    CompanyPriority.NORMAL: 0.0,
    CompanyPriority.LOW: -10.0,
}

RECENT_POSTING_DAYS = 3
STALE_POSTING_DAYS = 30


def compute_analysis_priority(
    *,
    posting: RawJobPosting,
    search_profile: SearchProfile | None,
    watchlist_entry: CompanyWatchlistEntry | None = None,
    now: datetime | None = None,
    candidate_preferred_locations: list[str] | None = None,
) -> float:
    now = now or datetime.now(UTC)
    score = 50.0
    title_lower = posting.title.lower()
    description_lower = posting.raw_description.lower()

    # --- Positive signals ---
    if any(kw in title_lower for kw in EARLY_CAREER_KEYWORDS):
        score += 15.0

    # search_profile is None for email-alert postings (Part 7 - no
    # SearchProfile at all for that path) - fall back to the candidate's
    # own `preferences.preferred_locations`, in list order, as the priority
    # ranking (Part 9: Melbourne/Victoria highest, then Hobart/Tasmania,
    # then Sydney/NSW, then Brisbane/QLD).
    if search_profile is not None and search_profile.locations and posting.location:
        location_norm = normalize_text(posting.location)
        priorities = search_profile.location_priority
        matched_priority_locations = [
            loc for loc in search_profile.locations if normalize_text(loc) in location_norm
        ]
        if matched_priority_locations:
            ranks = [priorities.get(loc, 99) for loc in matched_priority_locations]
            best_rank = min(ranks) if ranks else 99
            score += 20.0 if best_rank <= 1 else 12.0 if best_rank <= 3 else 6.0
    elif search_profile is None and candidate_preferred_locations and posting.location:
        location_norm = normalize_text(posting.location)
        matched_ranks = [
            rank
            for rank, loc in enumerate(candidate_preferred_locations)
            if normalize_text(loc) in location_norm
        ]
        if matched_ranks:
            best_rank = min(matched_ranks)
            score += 20.0 if best_rank == 0 else 12.0 if best_rank <= 2 else 6.0

    if posting.published_at is not None:
        age_days = (now - posting.published_at).days
        if age_days <= RECENT_POSTING_DAYS:
            score += 10.0
        elif age_days >= STALE_POSTING_DAYS:
            score -= 15.0

    if posting.source_type in DIRECT_SOURCE_TYPES:
        score += 8.0

    if watchlist_entry is not None:
        score += COMPANY_PRIORITY_BONUS.get(watchlist_entry.priority, 0.0)

    if search_profile is not None:
        relevant_keywords = [
            kw for group in search_profile.all_keyword_groups() for kw in group.keywords
        ]
        if any(normalize_text(kw) in title_lower for kw in relevant_keywords):
            score += 10.0

    # --- Negative signals ---
    if any(kw in title_lower for kw in SENIOR_TITLE_KEYWORDS):
        score -= 30.0

    max_years = max_years_mentioned(description_lower)
    if max_years is not None and max_years >= 8:
        score -= 20.0
    elif max_years is not None and max_years >= 5:
        score -= 8.0

    return round(max(0.0, min(100.0, score)), 1)
