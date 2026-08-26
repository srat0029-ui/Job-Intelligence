"""API request/response DTOs that don't map 1:1 onto a domain model.

Domain models (Candidate, Job, JobAnalysis, ...) are used directly as
response models elsewhere - they're already validated Pydantic models with
no framework coupling, so wrapping them in a parallel set of "API schemas"
would just be duplication. This module only holds the handful of shapes
that are genuinely request-only (e.g. "create a job from pasted text").
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import ApplicationStatus, ResearchSourceType
from app.domain.source_health import SourceHealth


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


class RunDiscoveryRequest(BaseModel):
    search_profile_ids: list[UUID] | None = Field(
        default=None,
        description="Run only these profiles. Omit to run every enabled search profile.",
    )


class SetApplicationStatusRequest(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=2000)


class CostSummary(BaseModel):
    spent_today_usd: float
    spent_all_time_usd: float
    daily_budget_usd: float | None


class DiscoveryDashboardStats(BaseModel):
    new_jobs_today: int
    high_priority_unreviewed: int
    unread_attention_count: int
    auto_discovery_enabled: bool
    last_scheduled_run_at: datetime | None
    next_scheduled_run_at: datetime | None
    source_health: list[SourceHealth]


# --- Milestone 4A: Application Intelligence ---


class AddResearchSourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    source_type: ResearchSourceType
    force_refresh: bool = False


class UpdateWorkspaceNotesRequest(BaseModel):
    notes: str = Field(default="", max_length=10_000)


class SubmitQuestionRequest(BaseModel):
    question_text: str = Field(min_length=1, max_length=5000)
