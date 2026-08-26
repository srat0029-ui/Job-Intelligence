"""Domain models for job-specific CV tailoring suggestions.

The candidate's existing structured profile (Project.highlights,
WorkExperience.summary, Skill, Education, Certification - see
app/domain/candidate.py) already *is* the canonical CV representation; this
module does not duplicate it into a second CV document. A
`CVTailoringSuggestion` proposes reworded text for one existing bullet/
section, always alongside the `original_text` it was derived from and the
candidate evidence IDs that ground it - never inventing a new bullet out of
nothing. `CVTailoringService` validates every suggestion (evidence IDs are
a subset of what was offered, no new metric/technology tokens appear that
aren't present in the original text or the cited evidence) before it is
ever persisted with `passed_grounding_check=True`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.application_workspace import GenerationMeta
from app.domain.enums import CVSection


class CVBulletSuggestion(BaseModel):
    section: CVSection
    source_ref_label: str  # e.g. the Project.name or WorkExperience.company this bullet is from
    original_text: str
    suggested_text: str
    relevance_rank: int = Field(ge=1)
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    passed_grounding_check: bool
    grounding_issues: list[str] = Field(default_factory=list)


class CVTailoringBatch(BaseModel):
    id: UUID | None = None
    workspace_id: UUID
    suggestions: list[CVBulletSuggestion] = Field(default_factory=list)
    section_emphasis: list[str] = Field(default_factory=list)  # e.g. ["projects", "skills"]
    source_evidence_ids: list[UUID] = Field(default_factory=list)
    meta: GenerationMeta
    created_at: datetime | None = None
