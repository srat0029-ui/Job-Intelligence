"""Domain models for the candidate profile.

These are plain Pydantic models with no SQLAlchemy/FastAPI dependency, so
they can be reused by the seed loader, services, evals, and API schemas
without coupling to any one layer.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, Field


class Education(BaseModel):
    id: UUID | None = None
    institution: str
    qualification: str
    field_of_study: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool = False
    notes: str | None = None


class WorkExperience(BaseModel):
    id: UUID | None = None
    company: str
    title: str
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool = False
    summary: str | None = None
    technologies: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """A single, citable piece of proof behind a skill or claim.

    This is the unit the matching engine cites against job requirements.
    Every positive claim the system makes about the candidate must trace
    back to one of these records - the LLM is never allowed to assert
    experience that isn't backed by an Evidence row.
    """

    id: UUID | None = None
    source_type: str  # EvidenceSourceType
    source_id: UUID | None = None  # e.g. the Project.id this evidence came from
    source_label: str  # human readable, e.g. "AFL Pricing & Market Intelligence Engine"
    statement: str  # e.g. "Built leakage-safe walk-forward evaluation pipelines in Python"
    skill_tags: list[str] = Field(default_factory=list)  # normalised skill/tech names this supports


class Skill(BaseModel):
    id: UUID | None = None
    name: str
    category: str | None = None  # e.g. "language", "framework", "tool", "domain"
    aliases: list[str] = Field(default_factory=list)  # e.g. ["JS"] for "JavaScript"
    proficiency: str | None = None  # e.g. "expert", "proficient", "familiar"


class Project(BaseModel):
    id: UUID | None = None
    name: str
    description: str
    technologies: list[str] = Field(default_factory=list)
    github_url: str | None = None
    highlights: list[str] = Field(default_factory=list)  # bullet-point evidence statements


class Achievement(BaseModel):
    id: UUID | None = None
    title: str
    description: str | None = None
    date: dt.date | None = None


class Certification(BaseModel):
    id: UUID | None = None
    name: str
    issuer: str | None = None
    date: dt.date | None = None
    credential_url: str | None = None


class CandidatePreferences(BaseModel):
    preferred_job_categories: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    # e.g. ["Australian Citizen", "No sponsorship required"]
    work_rights: list[str] = Field(default_factory=list)
    salary_expectation_min: int | None = None
    salary_expectation_max: int | None = None
    salary_currency: str = "AUD"
    remote_preference: str | None = None  # e.g. "hybrid", "remote", "onsite"
    # Technologies/domains the candidate actively wants more of - distinct
    # from `skills` (what they can demonstrably do): this is a preference
    # signal the pre-filter and future ranking can use, not evidence.
    preferred_technologies: list[str] = Field(default_factory=list)
    # e.g. ["sales", "recruitment"] - job categories to hard-exclude during
    # automated discovery, regardless of otherwise-good keyword matches.
    excluded_job_types: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    id: UUID | None = None
    name: str
    email: str | None = None
    summary: str | None = None
    strengths: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    work_history: list[WorkExperience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    preferences: CandidatePreferences = Field(default_factory=CandidatePreferences)
