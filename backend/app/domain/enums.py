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


class Recommendation(str, Enum):
    STRONG_APPLY = "strong_apply"
    APPLY = "apply"
    STRETCH = "stretch"
    LOW_PRIORITY = "low_priority"


class AIOperationType(str, Enum):
    JOB_EXTRACTION = "job_extraction"
    REQUIREMENT_MATCHING = "requirement_matching"


class AITraceStatus(str, Enum):
    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    PROVIDER_ERROR = "provider_error"
    RETRIED_SUCCESS = "retried_success"


class JobSourceType(str, Enum):
    MANUAL = "manual"
    # Future adapters - not implemented in V1, listed so the schema/UI can
    # already model "where did this job come from" without a migration later.
    SEEK = "seek"
    LINKEDIN = "linkedin"
    COMPANY_CAREER_PAGE = "company_career_page"
    GRADCONNECTION = "gradconnection"
    PROSPLE = "prosple"
    INDEED = "indeed"
    EMAIL = "email"
