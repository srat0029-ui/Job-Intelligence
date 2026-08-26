"""Domain model for the one-click Application Pack - the consolidated,
simplified view of Application Intelligence for the main product
experience.

This is a pure presentation composition over already-persisted artefacts
(ApplicationStrategy, CVTailoringBatch, CoverLetter, ApplicationBrief) - it
generates nothing itself and adds no new grounding rules. The detailed,
tab-by-tab Application Workspace (research/strategy/CV/questions/cover
letter individually) remains available underneath for anyone who wants to
inspect or regenerate a single piece; this is just the fast, single-screen
path most people want by default. See
app/services/application_workflow_service.py::prepare_application_pack.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.application_brief import ApplicationBrief
from app.domain.cv_tailoring import CVBulletSuggestion
from app.domain.enums import ApplicationStatus


class ApplicationPack(BaseModel):
    workspace_id: UUID
    job_id: UUID
    job_title: str
    company: str
    original_url: str | None = None
    application_status: ApplicationStatus | None = None
    brief: ApplicationBrief
    cv_suggestions: list[CVBulletSuggestion] = Field(default_factory=list)
    cv_reviewer_result: str | None = None
    cover_letter_body: str | None = None
    cover_letter_reviewer_result: str | None = None
    cover_letter_reviewer_issues: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None
