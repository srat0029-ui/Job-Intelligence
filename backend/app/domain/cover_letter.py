"""Domain model for generated cover letters.

Never submitted or emailed automatically - this is a drafting aid only,
persisted with full version history so a regeneration never silently loses
a prior draft the user preferred.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.application_workspace import GenerationMeta


class CoverLetter(BaseModel):
    id: UUID | None = None
    workspace_id: UUID
    body: str
    source_evidence_ids: list[UUID] = Field(default_factory=list)
    source_research_claim_ids: list[UUID] = Field(default_factory=list)
    meta: GenerationMeta
    created_at: datetime | None = None
