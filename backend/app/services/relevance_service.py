"""Cheap, deterministic relevance gate for email-sourced job alerts (SEEK/
LinkedIn) - runs before any AI call, so an inbox full of alert emails never
turns into an inbox full of AI spend.

Deliberately **not** applied to the existing Adzuna/company-watchlist paths
(see `DiscoveryService._process_posting`) - those already have their own
working, already-tested targeting via `SearchProfile` keywords/locations
plus `evaluate_prefilter`'s `max_experience_level`. Retrofitting this fixed
role-family taxonomy onto them risks silently rejecting real jobs that
already pass today. Email alerts have no SearchProfile at all, so this is
their only pre-AI gate - which is exactly the point: the candidate profile
alone (not a configured profile) decides what's relevant.

Role families and rejected-keyword lists are plain data below, not
scattered conditionals through the codebase - see Part 7 of the
simplification brief. Reuses (never duplicates) the seniority-detection
logic already in prefilter_service.py.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.candidate import Candidate
from app.ingestion.job_source import RawJobPosting
from app.services.prefilter_service import (
    contains_any,
    max_years_mentioned,
    title_implies_senior,
)

MAX_YEARS_FOR_RELEVANCE = 5


class RoleFamily(BaseModel):
    name: str
    keywords: list[str]


# One entry per family named in the brief - keywords cover the family's own
# graduate/junior/associate variants plus enough of the plain title (e.g.
# "software engineer") that a genuinely early-career posting isn't missed
# just because it didn't say "graduate" (Part 8: don't require the literal
# word if the role is otherwise early-career).
ROLE_FAMILIES: list[RoleFamily] = [
    RoleFamily(
        name="AI / Machine Learning",
        keywords=[
            "ai engineer",
            "machine learning engineer",
            "ml engineer",
            "artificial intelligence",
            "machine learning",
            "nlp engineer",
            "computer vision",
        ],
    ),
    RoleFamily(
        name="Data",
        keywords=[
            "data scientist",
            "data analyst",
            "data engineer",
            "data analytics",
            "analytics analyst",
            "business intelligence analyst",
        ],
    ),
    RoleFamily(
        name="Software",
        keywords=[
            "software engineer",
            "software developer",
            "developer",
            "full stack",
            "full-stack",
            "backend engineer",
            "frontend engineer",
            "web developer",
        ],
    ),
    RoleFamily(
        name="Technology Consulting",
        keywords=[
            "technology consultant",
            "technical consultant",
            "digital consultant",
            "technology analyst",
            "technology graduate",
            "consulting analyst",
        ],
    ),
    RoleFamily(
        name="Cyber Security",
        keywords=[
            "cyber security",
            "cybersecurity",
            "security analyst",
            "soc analyst",
            "information security",
        ],
    ),
    RoleFamily(
        name="Cloud / Systems",
        keywords=[
            "cloud engineer",
            "systems engineer",
            "infrastructure engineer",
            "devops",
            "cloud",
            "site reliability",
            "solutions architect",
            "architect",
        ],
    ),
]

# Part 10's explicit examples of what should NOT appear - checked against
# the title only (a data-analyst role that happens to mention "marketing"
# in its description shouldn't be rejected; a title that IS a marketing
# role should be). Never fires if a role-family keyword also matches the
# title, so a genuinely adjacent tech role is never lost to an incidental
# word (e.g. "Data Analyst - Marketing Team").
IRRELEVANT_TITLE_KEYWORDS = [
    "sales",
    "account executive",
    "accountant",
    "accounting",
    "marketing",
    "mechanical engineer",
    "civil engineer",
    "electrical engineer",
    "nurse",
    "clinical",
    "healthcare assistant",
    "physiotherapist",
    "receptionist",
    "retail",
    "hospitality",
    "warehouse",
    "forklift",
    "childcare",
    "aged care",
    "real estate",
    "recruitment consultant",
]

# Rejected on their own, unconditionally - matches Part 8's list directly
# (SENIOR_TITLE_KEYWORDS from prefilter_service already covers
# senior/lead/principal/director/head of/staff engineer/vp/chief; this adds
# the remaining Part-8 terms that constant doesn't carry, since that
# constant is shared with the already-tested Adzuna/watchlist path and
# shouldn't be widened for everyone just for the email path's stricter ask).
_EMAIL_ADDITIONAL_HARD_SENIOR_KEYWORDS = ["manager", "staff", "staff-level"]

# Only rejected when *also* paired with an experience signal - a bare
# "Solutions Architect Graduate Program" shouldn't be rejected just for
# containing the word (Part 8: "architect roles requiring substantial
# experience", not "architect roles").
_CONDITIONAL_SENIOR_KEYWORDS = ["architect"]


class RelevanceResult(BaseModel):
    passed: bool
    score: float
    reason: str | None = None
    matched_family: str | None = None


def _matched_role_family(haystack: str) -> str | None:
    for family in ROLE_FAMILIES:
        if any(keyword in haystack for keyword in family.keywords):
            return family.name
    return None


def evaluate_relevance(posting: RawJobPosting, candidate: Candidate) -> RelevanceResult:
    title = (posting.title or "").lower()
    description = (posting.raw_description or "").lower()
    combined = f"{title} {description}"

    family_from_title = _matched_role_family(title)
    family_from_either = family_from_title or _matched_role_family(combined)

    # 1. Seniority - reuse the existing detector, plus the email path's own
    # small additional keyword set, plus the conditional "architect" case.
    senior_keyword = title_implies_senior(posting.title or "") or contains_any(
        posting.title or "", _EMAIL_ADDITIONAL_HARD_SENIOR_KEYWORDS
    )
    if senior_keyword:
        return RelevanceResult(
            passed=False,
            score=0.0,
            reason=f"Title contains '{senior_keyword}', which reads as a senior-level role.",
        )

    conditional_keyword = contains_any(posting.title or "", _CONDITIONAL_SENIOR_KEYWORDS)
    years = max_years_mentioned(description)
    if conditional_keyword and years is not None and years > MAX_YEARS_FOR_RELEVANCE:
        return RelevanceResult(
            passed=False,
            score=0.0,
            reason=(
                f"Title contains '{conditional_keyword}' and the description mentions "
                f"{years}+ years of experience."
            ),
        )

    if years is not None and years > MAX_YEARS_FOR_RELEVANCE:
        return RelevanceResult(
            passed=False,
            score=0.0,
            reason=f"Description mentions {years}+ years of experience.",
        )

    # 2. Explicit irrelevant-role rejection (title only, unless a role
    # family also matches the title - stay generous with adjacent roles).
    irrelevant_keyword = contains_any(posting.title or "", IRRELEVANT_TITLE_KEYWORDS)
    if irrelevant_keyword and not family_from_title:
        return RelevanceResult(
            passed=False,
            score=0.0,
            reason=f"Title matches an irrelevant role keyword ('{irrelevant_keyword}').",
        )

    # 3. Generous relevance scoring: any role-family or preferred-technology
    # signal is enough to pass - the AI analysis pipeline does the real
    # fine-grained ranking afterward, this is only "worth analysing at all".
    score = 0.0
    reasons: list[str] = []
    if family_from_title:
        score += 60.0
        reasons.append(f"title matches the {family_from_title} family")
    elif family_from_either:
        score += 35.0
        reasons.append(f"description matches the {family_from_either} family")

    tech_matches = [
        tech
        for tech in candidate.preferences.preferred_technologies
        if tech.lower() in combined
    ]
    if tech_matches:
        score += min(len(tech_matches) * 10.0, 30.0)
        reasons.append(f"mentions {', '.join(tech_matches[:3])}")

    if score <= 0.0:
        return RelevanceResult(
            passed=False,
            score=0.0,
            reason="No target role family or preferred technology matched.",
        )

    return RelevanceResult(
        passed=True,
        score=min(score, 100.0),
        reason="Relevant: " + "; ".join(reasons),
        matched_family=family_from_either,
    )
