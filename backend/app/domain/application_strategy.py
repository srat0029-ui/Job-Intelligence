"""Domain model for the ApplicationStrategy artefact.

`application_priority` is copied straight from the existing, already-stored
`Recommendation`/`JobPriority` on the job's analysis/discovery record - this
module never computes a new fit number. Every factual/evidence-based field
(`lead_evidence_ids`, `source_research_claim_ids`) stores IDs, not restated
text, so a reader can always trace a claim back to its evidence or research
source.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.application_workspace import GenerationMeta


class ConcernItem(BaseModel):
    concern: str
    response_strategy: str


class ApplicationStrategy(BaseModel):
    id: UUID | None = None
    workspace_id: UUID
    gap_analysis_id: UUID

    positioning: str
    lead_evidence_ids: list[UUID] = Field(default_factory=list)  # 2-4 IDs
    skills_to_emphasise: list[str] = Field(default_factory=list)
    skills_to_deemphasise: list[str] = Field(default_factory=list)
    likely_concerns: list[ConcernItem] = Field(default_factory=list)
    motivation_themes: list[str] = Field(default_factory=list)

    # Copied from the existing analysis/discovery record, never recomputed.
    application_priority: str | None = None  # JobPriority value, if the job was discovered
    recommendation: str  # Recommendation value, from the existing FitScore

    source_evidence_ids: list[UUID] = Field(default_factory=list)
    source_research_claim_ids: list[UUID] = Field(default_factory=list)

    meta: GenerationMeta
    created_at: datetime | None = None
