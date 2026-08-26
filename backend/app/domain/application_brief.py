"""Domain model for the Application Brief - a read-before-applying summary.

Computed entirely from already-stored, already-grounded records (the job's
FitScore/match result, the ApplicationStrategy, and the ResearchClaims it
cites) - never its own LLM call, so it carries no fresh fabrication risk.
See app/services/application_brief_service.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BriefEvidenceItem(BaseModel):
    evidence_id: str
    label: str


class ApplicationBrief(BaseModel):
    why_this_role_fits: list[str] = Field(default_factory=list)
    best_evidence_to_use: list[BriefEvidenceItem] = Field(default_factory=list)
    key_gaps: list[str] = Field(default_factory=list)
    how_to_position: list[str] = Field(default_factory=list)
    company_talking_points: list[str] = Field(default_factory=list)
    likely_application_themes: list[str] = Field(default_factory=list)
