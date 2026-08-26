"""Domain models for jobs and their AI-extracted structured requirements."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import (
    ApplicationStatus,
    EmploymentType,
    JobSourceType,
    RequirementCategory,
    RequirementImportance,
    SeniorityLevel,
)


class Job(BaseModel):
    """A job posting as the user entered it - raw, unstructured."""

    id: UUID | None = None
    title: str
    company: str
    location: str | None = None
    source_url: str | None = None
    source_type: JobSourceType = JobSourceType.MANUAL
    raw_description: str
    application_status: ApplicationStatus | None = None
    created_at: str | None = None


class SalaryRange(BaseModel):
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    period: str | None = None  # e.g. "year", "hour"


class ExtractedRequirement(BaseModel):
    """A single requirement pulled out of the job description by the LLM.

    `category` determines which fit sub-score this feeds into during
    scoring. `raw_phrase` retains the exact wording so the UI can show the
    user the original text alongside the normalised `name`.
    """

    name: str  # normalised, e.g. "Python"
    raw_phrase: str  # e.g. "3+ years of Python development"
    category: RequirementCategory
    importance: RequirementImportance
    notes: str | None = None


class ExtractedJob(BaseModel):
    """Strongly typed, validated output of job-description extraction.

    This is the contract between the AI layer and the rest of the
    application - application logic (matching, scoring) only ever reads
    from this structure, never from raw model text.
    """

    title: str
    company: str
    location: str | None = None
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    salary: SalaryRange | None = None
    role_category: str | None = None  # inferred, e.g. "Backend Engineering", "Data Science"
    requirements: list[ExtractedRequirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    important_phrases: list[str] = Field(default_factory=list)
    extraction_summary: str | None = None  # short, user-facing, no chain-of-thought
