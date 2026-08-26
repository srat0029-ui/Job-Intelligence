"""Deterministic, pre-LLM rejection of clearly unsuitable postings.

This is the key cost-control architectural piece: every rule here is plain
Python string/regex matching against the raw posting text and the
candidate's/search profile's stored preferences - no LLM call happens until
a posting survives every rule. Rules are deliberately conservative (a
posting is only rejected on a strong, explicit signal) per the brief:
"Do not make the filtering so aggressive that potentially good stretch
roles are discarded."

Thresholds/keyword lists are module-level constants specifically so they're
easy to find and tune without hunting through the pipeline - the two
per-search-profile knobs the brief calls out explicitly
(`max_experience_level`, `excluded_keywords`) are real `SearchProfile`
fields; the rest (senior-title keywords, the "N+ years" ceiling, work-rights
phrasing) are constants below, not hidden magic numbers.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.domain.candidate import Candidate
from app.domain.discovery import SearchProfile
from app.domain.enums import SeniorityLevel
from app.ingestion.job_source import RawJobPosting

# Order matters: index = seniority rank, used to compare a posting's implied
# level against a search profile's configured ceiling.
SENIORITY_RANK: dict[SeniorityLevel, int] = {
    SeniorityLevel.INTERN: 0,
    SeniorityLevel.GRADUATE: 1,
    SeniorityLevel.JUNIOR: 2,
    SeniorityLevel.MID: 3,
    SeniorityLevel.SENIOR: 4,
    SeniorityLevel.LEAD: 5,
    SeniorityLevel.STAFF_PLUS: 6,
}

# Only titles containing these are treated as "clearly senior" for the
# purposes of the title-based rule - deliberately narrow so "Senior Analyst
# Program" style false positives are rare, and so a search profile with no
# `max_experience_level` set never rejects on this at all.
SENIOR_TITLE_KEYWORDS = [
    "senior",
    "sr.",
    "lead ",
    "principal",
    "director",
    "head of",
    "staff engineer",
    "vp ",
    "chief ",
]
SENIOR_TITLE_MIN_RANK = SENIORITY_RANK[SeniorityLevel.SENIOR]

# "8+ years", "10 years of experience", etc. Above this, a posting is
# rejected only when the search profile has an early-career ceiling.
MAX_ACCEPTABLE_YEARS_FOR_EARLY_CAREER = 5
MAX_ACCEPTABLE_YEARS_ABSOLUTE = 8
_YEARS_EXPERIENCE_RE = re.compile(r"(\d{1,2})\s*\+?\s*years?", re.IGNORECASE)

REMOTE_HINT_KEYWORDS = ["remote", "work from home", "wfh"]

# Conservative - only strong, unambiguous "you must already have the right
# to work here" phrasing. Absence of these phrases never triggers a
# rejection; presence only rejects if the candidate's declared work rights
# don't already cover it.
WORK_RIGHTS_REQUIRED_PHRASES = [
    "must have full working rights",
    "must have unrestricted working rights",
    "must be an australian citizen",
    "no visa sponsorship",
    "not able to provide sponsorship",
    "sponsorship is not available",
]


class PreFilterResult(BaseModel):
    passed: bool
    reason: str | None = None


def _contains_any(haystack: str, needles: list[str]) -> str | None:
    lowered = haystack.lower()
    for needle in needles:
        if needle.lower() in lowered:
            return needle
    return None


def _max_years_mentioned(text: str) -> int | None:
    years = [int(m.group(1)) for m in _YEARS_EXPERIENCE_RE.finditer(text)]
    return max(years) if years else None


def _title_implies_senior(title: str) -> str | None:
    return _contains_any(title, SENIOR_TITLE_KEYWORDS)


def _location_is_acceptable(posting: RawJobPosting, search_profile: SearchProfile) -> bool:
    if not search_profile.locations:
        return True  # no location constraint configured

    haystack = f"{posting.location or ''} {posting.raw_description}".lower()
    if any(loc.lower() in haystack for loc in search_profile.locations):
        return True
    if search_profile.include_remote and _contains_any(haystack, REMOTE_HINT_KEYWORDS):
        return True
    return False


def _work_rights_ok(posting: RawJobPosting, candidate: Candidate) -> tuple[bool, str | None]:
    phrase = _contains_any(posting.raw_description, WORK_RIGHTS_REQUIRED_PHRASES)
    if phrase is None:
        return True, None
    declared = " ".join(candidate.preferences.work_rights).lower()
    # If the candidate has declared ANY work-rights statement at all, trust
    # it (a real check happens later, per-requirement, in MatchingService)
    # - this rule exists only to catch the case where the candidate has
    # declared nothing and the posting is explicit about requiring it.
    if declared.strip():
        return True, None
    return False, phrase


def evaluate_prefilter(
    *,
    posting: RawJobPosting,
    candidate: Candidate,
    search_profile: SearchProfile,
) -> PreFilterResult:
    title = posting.title or ""
    description = posting.raw_description or ""

    excluded = _contains_any(title + " " + description, search_profile.excluded_keywords)
    if excluded:
        return PreFilterResult(
            passed=False, reason=f"Description/title contains excluded keyword '{excluded}'."
        )

    excluded_job_type = _contains_any(title, candidate.preferences.excluded_job_types)
    if excluded_job_type:
        return PreFilterResult(
            passed=False,
            reason=f"Title matches a job type you've excluded ('{excluded_job_type}').",
        )

    if search_profile.max_experience_level is not None:
        ceiling_rank = SENIORITY_RANK[search_profile.max_experience_level]

        senior_keyword = _title_implies_senior(title)
        if senior_keyword and ceiling_rank < SENIOR_TITLE_MIN_RANK:
            return PreFilterResult(
                passed=False,
                reason=(
                    f"Title contains '{senior_keyword}', which exceeds the configured "
                    f"max experience level ({search_profile.max_experience_level.value})."
                ),
            )

        years_ceiling = (
            MAX_ACCEPTABLE_YEARS_FOR_EARLY_CAREER
            if ceiling_rank <= SENIORITY_RANK[SeniorityLevel.JUNIOR]
            else MAX_ACCEPTABLE_YEARS_ABSOLUTE
        )
        max_years = _max_years_mentioned(description)
        if max_years is not None and max_years > years_ceiling:
            return PreFilterResult(
                passed=False,
                reason=(
                    f"Description requires {max_years}+ years of experience, above the "
                    f"{years_ceiling}-year ceiling for max experience level "
                    f"'{search_profile.max_experience_level.value}'."
                ),
            )

    if not _location_is_acceptable(posting, search_profile):
        return PreFilterResult(
            passed=False,
            reason=(
                f"Location '{posting.location or 'unknown'}' doesn't match any configured "
                "location and remote work wasn't indicated."
            ),
        )

    ok, phrase = _work_rights_ok(posting, candidate)
    if not ok:
        return PreFilterResult(
            passed=False,
            reason=(
                f"Posting explicitly requires work rights ('{phrase}') and no work-rights "
                "preference is recorded on the candidate profile."
            ),
        )

    return PreFilterResult(passed=True)
