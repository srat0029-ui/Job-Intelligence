"""Domain models for requirement-by-requirement matching output."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import EvidenceTier, RequirementCategory, RequirementImportance


class RequirementMatch(BaseModel):
    """The result of matching one job requirement against candidate evidence.

    `evidence_ids` may only contain IDs drawn from the candidate evidence set
    that was actually provided to the LLM during matching - this is enforced
    by validation in MatchingService, not merely by prompt instruction, so
    the LLM cannot fabricate evidence.
    """

    requirement_name: str
    category: RequirementCategory
    importance: RequirementImportance
    tier: EvidenceTier
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(default_factory=list)
    evidence_summary: str | None = None  # short, user-facing explanation
    is_gap: bool = False


class MatchResult(BaseModel):
    """All requirement matches for one job analysis."""

    matches: list[RequirementMatch] = Field(default_factory=list)

    @property
    def gaps(self) -> list[RequirementMatch]:
        return [m for m in self.matches if m.is_gap]

    @property
    def strengths(self) -> list[RequirementMatch]:
        return [m for m in self.matches if m.tier == "explicit" and not m.is_gap]
