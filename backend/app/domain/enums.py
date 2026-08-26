"""Shared enums used across domain, DB, and API layers.

Kept in one module so the DB layer, Pydantic schemas, and the frontend
TypeScript types (generated/mirrored by hand) all agree on the same string
values.
"""

from enum import Enum


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    CASUAL = "casual"
    UNKNOWN = "unknown"


class SeniorityLevel(str, Enum):
    INTERN = "intern"
    GRADUATE = "graduate"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    STAFF_PLUS = "staff_plus"
    UNKNOWN = "unknown"


class RequirementCategory(str, Enum):
    """What kind of requirement this is - drives which fit sub-score it feeds."""

    TECHNICAL_SKILL = "technical_skill"
    TECHNOLOGY = "technology"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    SOFT_SKILL = "soft_skill"
    WORK_RIGHTS = "work_rights"
    LOCATION = "location"


class RequirementImportance(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class EvidenceTier(str, Enum):
    """How strongly candidate evidence supports a requirement.

    This is the anti-hallucination backbone of the system: the LLM may only
    select this tier plus cite evidence IDs from a fixed list we hand it. It
    is never allowed to describe experience the candidate doesn't have on
    record.
    """

    EXPLICIT = "explicit"          # direct, named evidence (e.g. "Python" <-> "Python" project tag)
    TRANSFERABLE = "transferable"  # related/adjacent evidence (e.g. R <-> Python, both stats-heavy)
    WEAK_INFERENCE = "weak_inference"  # plausible but thin, e.g. only implied by project domain
    NO_EVIDENCE = "no_evidence"    # genuine gap


class EvidenceSourceType(str, Enum):
    PROJECT = "project"
    WORK_EXPERIENCE = "work_experience"
    EDUCATION = "education"
    SKILL_DECLARATION = "skill_declaration"
    ACHIEVEMENT = "achievement"
    CERTIFICATION = "certification"
    # Provenance for evidence pulled in automatically rather than typed by
    # hand - lets the UI/matching engine show "where did this come from"
    # regardless of how a profile was built up over time.
    CV = "cv"
    GITHUB = "github"


class Recommendation(str, Enum):
    STRONG_APPLY = "strong_apply"
    APPLY = "apply"
    STRETCH = "stretch"
    LOW_PRIORITY = "low_priority"


class AIOperationType(str, Enum):
    JOB_EXTRACTION = "job_extraction"
    REQUIREMENT_MATCHING = "requirement_matching"
    CV_EXTRACTION = "cv_extraction"
    COMPANY_RESEARCH_SYNTHESIS = "company_research_synthesis"
    GAP_ANALYSIS = "gap_analysis"
    APPLICATION_STRATEGY = "application_strategy"
    CV_TAILORING = "cv_tailoring"
    APPLICATION_QUESTION = "application_question"
    COVER_LETTER = "cover_letter"
    GROUNDING_REVIEW = "grounding_review"


class AITraceStatus(str, Enum):
    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    PROVIDER_ERROR = "provider_error"
    RETRIED_SUCCESS = "retried_success"


class JobSourceType(str, Enum):
    MANUAL = "manual"
    ADZUNA = "adzuna"
    LEVER = "lever"
    GREENHOUSE = "greenhouse"
    # Future adapters - not implemented yet, listed so the schema/UI can
    # already model "where did this job come from" without a migration later.
    SEEK = "seek"
    LINKEDIN = "linkedin"
    COMPANY_CAREER_PAGE = "company_career_page"
    GRADCONNECTION = "gradconnection"
    PROSPLE = "prosple"
    INDEED = "indeed"
    EMAIL = "email"


class ATSType(str, Enum):
    """Applicant tracking systems CompanyWatchlist entries can target.
    Deliberately a small, explicit set - adding a new ATS is one new enum
    value + one new JobSource implementation, never special-cased logic
    scattered through the generic discovery orchestrator."""

    LEVER = "lever"
    GREENHOUSE = "greenhouse"


class CompanyPriority(str, Enum):
    """Boosts ANALYSIS PRIORITY only (which jobs get analysed first when
    budget-constrained) - never the final candidate fit score. See
    app/services/analysis_priority_service.py."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class SourceHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    UNKNOWN = "unknown"


class DuplicateMatchStage(str, Enum):
    """How a source observation was matched to its canonical DiscoveredJob -
    stored per observation so a merge decision is always auditable."""

    EXACT_ID = "exact_id"
    CANONICAL_URL = "canonical_url"
    DETERMINISTIC_FINGERPRINT = "deterministic_fingerprint"
    FUZZY = "fuzzy"
    ORIGINAL = "original"  # the first-seen observation - not a "match" at all


class AttentionItemType(str, Enum):
    HIGH_PRIORITY_JOB = "high_priority_job"
    WATCHLIST_COMPANY_POSTING = "watchlist_company_posting"
    ANALYSIS_FAILURES = "analysis_failures"
    SOURCE_UNHEALTHY = "source_unhealthy"


class AttentionItemStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"


class DiscoveredJobStatus(str, Enum):
    """Where one discovered posting is in the discovery -> analysis pipeline.

    A job only reaches ANALYSING/ANALYSED by being promoted into the
    existing `jobs` table and run through the existing
    AnalysisOrchestrator - this enum tracks the discovery-side workflow
    around that, not a parallel analysis system.
    """

    DISCOVERED = "discovered"
    DUPLICATE = "duplicate"
    PREFILTER_REJECTED = "prefilter_rejected"
    AWAITING_ANALYSIS = "awaiting_analysis"
    ANALYSING = "analysing"
    ANALYSED = "analysed"
    ANALYSIS_FAILED = "analysis_failed"
    ARCHIVED = "archived"


class JobPriority(str, Enum):
    """Higher-level triage bucket layered on top of the existing fit score,
    for the discovery feed. Deliberately separate from `Recommendation`
    (which stays as the per-analysis, gap-aware recommendation) - this is a
    coarser, score-only bucket used purely for sorting/skimming a feed of
    many opportunities at once."""

    APPLY_ASAP = "apply_asap"
    STRONG_APPLY = "strong_apply"
    APPLY = "apply"
    STRETCH = "stretch"
    LOW_PRIORITY = "low_priority"


class ApplicationStatus(str, Enum):
    INTERESTED = "interested"
    APPLYING = "applying"
    APPLIED = "applied"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"
    WITHDRAWN = "withdrawn"
    IGNORED = "ignored"


class DiscoveryRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# --- Milestone 4A: Application Intelligence ---


class ResearchSourceType(str, Enum):
    """What kind of page a ResearchSource was fetched from - drives source
    quality ranking (see app/services/company_research_service.py:
    SOURCE_QUALITY_RANK). Kept separate from claim confidence: a claim's
    confidence is about how clearly the text supports it, source quality is
    about how trustworthy the origin of the text is."""

    OFFICIAL_WEBSITE = "official_website"
    CAREERS_PAGE = "careers_page"
    ENGINEERING_BLOG = "engineering_blog"
    PRESS_RELEASE = "press_release"
    NEWS = "news"
    COMPANY_DIRECTORY = "company_directory"
    OTHER = "other"


class SourceQualityTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ClaimVerificationStatus(str, Enum):
    """Whether a ResearchClaim is directly stated by its source, merely a
    reasonable inference from it, or could not be grounded at all (and so
    must never be presented as established fact)."""

    VERIFIED_FACT = "verified_fact"
    REASONABLE_INFERENCE = "reasonable_inference"
    UNKNOWN = "unknown"


class ResearchFetchStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class GapStrategyCategory(str, Enum):
    """How to handle a genuine requirement gap in application material -
    never invent evidence to close it, only choose an honest framing."""

    ACKNOWLEDGE_HONESTLY = "acknowledge_honestly"
    DEMONSTRATE_TRANSFERABLE = "demonstrate_transferable"
    PROVIDE_PROJECT_EVIDENCE = "provide_project_evidence"
    SHOW_RAPID_LEARNING = "show_rapid_learning"
    DO_NOT_ADDRESS = "do_not_address"


class EvidenceStrength(str, Enum):
    """Application-focused classification of how well candidate evidence
    covers one important job requirement - extends (does not replace) the
    existing RequirementMatch.tier used by the core scoring pipeline."""

    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"
    GAP = "gap"


class GenerationStatus(str, Enum):
    """Lifecycle of one generated application artefact (a CV tailoring
    batch, a cover letter, a question response, ...)."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    NEEDS_REVIEW = "needs_review"
    ARCHIVED = "archived"  # superseded by a newer version, never deleted


class ReviewVerdict(str, Enum):
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"


class QuestionType(str, Enum):
    MOTIVATION = "motivation"
    COMPANY_MOTIVATION = "company_motivation"
    TECHNICAL_EXPERIENCE = "technical_experience"
    BEHAVIOURAL = "behavioural"
    VALUES = "values"
    TEAMWORK = "teamwork"
    LEADERSHIP = "leadership"
    PROBLEM_SOLVING = "problem_solving"
    LEARNING = "learning"
    PROJECT_EXPERIENCE = "project_experience"
    WORK_RIGHTS = "work_rights"
    SALARY = "salary"
    GENERAL_BACKGROUND = "general_background"


class CVSection(str, Enum):
    SUMMARY = "summary"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    PROJECT = "project"
    SKILL = "skill"
    CERTIFICATION = "certification"


class GeographicEligibility(str, Enum):
    """A hard, deterministic eligibility gate - NOT a scoring preference.

    Computed once per posting (see app/services/location_service.py) right
    after source normalisation, identically regardless of source (Adzuna,
    Lever, Greenhouse, any future adapter). Only ELIGIBLE postings ever
    reach the recommended feed or get analysed - see
    DiscoveryService._process_posting. INELIGIBLE and LOCATION_UNCONFIRMED
    are kept distinct so a "confidently overseas" posting can be told apart
    from a genuinely ambiguous one during debugging, even though both are
    hidden from the default feed the same way."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    LOCATION_UNCONFIRMED = "location_unconfirmed"
