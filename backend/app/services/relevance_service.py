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
# word if the role is otherwise early-career). Broadened beyond exact
# "Engineer"/"Scientist" title phrasing (real postings use "Forward
# Deployed AI Scientist", "Applied Scientist", "Analyst", "Consultant" for
# the same underlying work) - see relevance_service's own docstring/the
# recommendation-quality review this was calibrated against.
ROLE_FAMILIES: list[RoleFamily] = [
    RoleFamily(
        name="AI / Machine Learning",
        keywords=[
            "ai engineer",
            "ai scientist",
            "ai analyst",
            "ai developer",
            "machine learning engineer",
            "machine learning scientist",
            "ml engineer",
            "ml scientist",
            "applied scientist",
            "artificial intelligence",
            "machine learning",
            "nlp engineer",
            "computer vision",
            "forward deployed ai",
            "genai",
            "generative ai",
            "llm engineer",
            "prompt engineer",
        ],
    ),
    RoleFamily(
        name="Data Science",
        keywords=[
            "data scientist",
            "data science",
            "quantitative researcher",
        ],
    ),
    RoleFamily(
        name="Data Analytics",
        keywords=[
            "data analyst",
            "data analytics",
            "analytics analyst",
            "analytics engineer",
            "insights analyst",
            "business intelligence analyst",
            "bi analyst",
        ],
    ),
    RoleFamily(
        name="Data Engineering",
        keywords=[
            "data engineer",
            "data engineering",
            "analytics engineer",
        ],
    ),
    RoleFamily(
        name="Quant / Technical Analytics",
        keywords=[
            "quantitative analyst",
            "quant analyst",
            "quantitative developer",
            "quantitative associate",
            "quant developer",
        ],
    ),
    RoleFamily(
        name="Software Engineering",
        keywords=[
            "software engineer",
            "software developer",
            "developer",
            "full stack",
            "full-stack",
            "backend engineer",
            "backend developer",
            "frontend engineer",
            "frontend developer",
            "web developer",
            "application developer",
            "programmer",
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
            "solutions consultant",
            "forward deployed",
        ],
    ),
    RoleFamily(
        name="Cyber Security",
        keywords=[
            "cyber security",
            "cybersecurity",
            "security analyst",
            "security engineer",
            "soc analyst",
            "information security",
            "penetration tester",
        ],
    ),
    RoleFamily(
        name="Cloud / Systems",
        keywords=[
            "cloud engineer",
            "systems engineer",
            "infrastructure engineer",
            "platform engineer",
            "devops",
            "cloud",
            "site reliability",
            "solutions architect",
            "architect",
        ],
    ),
]

# Explicit early-career signals (Part 1 of the recommendation-quality
# review) - a title carrying one of these is strong evidence the role is
# worth considering even when it doesn't match any ROLE_FAMILIES phrase
# outright (a company-wide "Graduate Program"/"Graduate Campaign" rarely
# says "Software Engineer" anywhere in its own title).
EARLY_CAREER_INDICATORS = [
    "graduate program",
    "graduate campaign",
    "graduate scheme",
    "graduate",
    "junior",
    "associate",
    "entry level",
    "entry-level",
    "early career",
    "intern",
    "internship",
    "trainee",
    "new grad",
]

# Generic technology/technical-stream signal, checked against the combined
# title+description when an early-career indicator is present but no
# specific ROLE_FAMILIES phrase matched - lets a broad "Graduate Analyst -
# Technology" or "Technology Graduate Program" through without requiring
# the exact role title, while still requiring *some* technical signal so a
# graduate program in an unrelated stream (sales, finance, HR) isn't let
# through on the word "graduate" alone.
GENERIC_TECHNICAL_STREAM_KEYWORDS = [
    "technology",
    "tech stream",
    "digital",
    "data",
    "software",
    "cyber",
    "security",
    "artificial intelligence",
    "machine learning",
    "analytics",
    "engineering",
    "information technology",
    "computer science",
    "systems",
    "cloud",
    "quant",
    "programming",
    "developer",
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

    # Generic graduate-program fallback (Part 1): a broad "Graduate
    # Analyst - Technology" or "Technology Graduate Program" title rarely
    # matches a specific ROLE_FAMILIES phrase (it doesn't say "Software
    # Engineer" or "Data Scientist" anywhere), but is still worth
    # considering when it carries both an explicit early-career signal AND
    # some generic technical-stream signal. Never fires on "graduate" alone
    # - a graduate program in an unrelated stream (sales, finance, HR) with
    # no technical signal at all is correctly left unmatched.
    graduate_program_match = False
    if not family_from_either:
        early_career_signal = contains_any(title, EARLY_CAREER_INDICATORS)
        technical_stream_signal = contains_any(combined, GENERIC_TECHNICAL_STREAM_KEYWORDS)
        if early_career_signal and technical_stream_signal:
            graduate_program_match = True
            family_from_either = "Technology Graduate Program"

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
    # Deliberately NOT bypassed by the generic graduate-program fallback
    # below: an explicitly irrelevant title (e.g. "Graduate Marketing
    # Coordinator") must stay rejected even if the description happens to
    # mention an incidental technical-sounding word ("digital marketing").
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
    elif graduate_program_match:
        score += 40.0
        reasons.append("early-career signal + technical stream (generic graduate program)")
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
