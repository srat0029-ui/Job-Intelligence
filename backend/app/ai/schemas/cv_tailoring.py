"""Structured output contract for CV tailoring suggestions.

`CVTailoringService` validates every item after generation: evidence IDs
must be a subset of what was offered, and `suggested_text` is scanned for
metric/technology tokens absent from both `original_text` and the cited
evidence - see its module docstring for the exact grounding checks.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import CVSection


class LLMCVBulletSuggestion(BaseModel):
    section: CVSection
    source_ref_label: str = Field(
        description="The exact project name / company name this bullet is about, copied "
        "from the candidate profile provided."
    )
    original_text: str = Field(
        description="Copied exactly from the candidate profile provided - never invented."
    )
    suggested_text: str = Field(
        description="A reworded version emphasising relevance to this job. Must not add any "
        "technology, metric, or claim not already present in original_text or the cited "
        "evidence statements."
    )
    relevance_rank: int = Field(ge=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class LLMCVTailoringOutput(BaseModel):
    suggestions: list[LLMCVBulletSuggestion] = Field(default_factory=list)
    section_emphasis: list[str] = Field(
        default_factory=list,
        description="e.g. ['projects', 'skills'] - which sections to lead with.",
    )
