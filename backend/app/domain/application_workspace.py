"""Domain model for the Application Workspace.

An `ApplicationWorkspace` is the home for everything involved in preparing
one application - it is associated with the existing `Job`/`JobAnalysis`
records rather than creating a second job system: `job_id` points straight
at the canonical `jobs` row (the same one the manual-analysis and discovery
pipelines already promote postings into). One workspace per job.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationWorkspace(BaseModel):
    id: UUID | None = None
    job_id: UUID
    notes: str | None = None
    research_company_name: str | None = None  # resolved company name research is cached under
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GenerationMeta(BaseModel):
    """Shared provenance/versioning fields every generated artefact carries -
    embedded (not inherited) since these are plain data models, not classes
    with shared behaviour."""

    version: int = Field(ge=1, default=1)
    status: str  # GenerationStatus
    prompt_version: str
    model: str
    generated_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    reviewer_result: str | None = None  # ReviewVerdict, set after grounding review
    reviewer_issues: list[str] = Field(default_factory=list)
    regeneration_attempt: int = 1
