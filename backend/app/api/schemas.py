"""API request/response DTOs that don't map 1:1 onto a domain model.

Domain models (Candidate, Job, JobAnalysis, ...) are used directly as
response models elsewhere - they're already validated Pydantic models with
no framework coupling, so wrapping them in a parallel set of "API schemas"
would just be duplication. This module only holds the handful of shapes
that are genuinely request-only (e.g. "create a job from pasted text").
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=1000)
    raw_description: str = Field(min_length=1)


class JobListItem(BaseModel):
    id: str
    title: str
    company: str
    location: str | None
    created_at: str | None
    latest_overall_score: float | None = None
    latest_recommendation: str | None = None


class DashboardStats(BaseModel):
    total_jobs: int
    total_analyses: int
    strongest_opportunities: list[JobListItem]
    recent_analyses: list[JobListItem]
    score_distribution: dict[str, int]  # bucket label -> count
