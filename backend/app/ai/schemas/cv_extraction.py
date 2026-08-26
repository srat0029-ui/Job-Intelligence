"""Structured output contract for CV/resume extraction.

Narrower than the full `Candidate` domain model on purpose: a CV can
reliably supply identity/education/work-history/projects/skills/
achievements/certifications and evidence statements, but NOT preferences
(salary expectations, remote preference, excluded job types) - those stay
manually curated and are never inferred from a resume. `evidence[].source_type`
is forced to "cv" in code after extraction (see ResumeFileSource), never
trusted from the model, so provenance is guaranteed correct regardless of
what the LLM outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.candidate import (
    Achievement,
    Certification,
    Education,
    Evidence,
    Project,
    Skill,
    WorkExperience,
)


class CVExtraction(BaseModel):
    name: str | None = None
    email: str | None = None
    summary: str | None = None
    education: list[Education] = Field(default_factory=list)
    work_history: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
