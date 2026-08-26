"""Domain models for application-focused gap analysis.

Extends (does not replace) the existing `MatchResult`/`RequirementMatch`
from the core evidence-matching pipeline: `GapAnalysis` is built from an
already-computed `JobAnalysis` and only adds an application *strategy*
layer - how to handle each genuine gap in application material - never a
second scoring system. `EvidenceStrength` reclassifies each requirement's
existing `RequirementMatch` for application purposes (STRONG/PARTIAL/WEAK/
GAP) using the same tier/is_gap data already stored, and only genuine gaps
get an LLM-proposed `GapStrategyCategory` plus one grounded guidance
sentence - which must never convert transferable evidence into a claim of
direct experience.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import EvidenceStrength, GapStrategyCategory, RequirementImportance


class RequirementCoverage(BaseModel):
    requirement_name: str
    importance: RequirementImportance
    strength: EvidenceStrength


class GapStrategyItem(BaseModel):
    """One genuine gap plus how the application should honestly handle it."""

    requirement_name: str
    strategy_category: GapStrategyCategory
    guidance: str  # concise, user-facing, grounded only in provided adjacent evidence
    adjacent_evidence_ids: list[UUID] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    id: UUID | None = None
    workspace_id: UUID
    job_analysis_id: UUID
    coverage: list[RequirementCoverage] = Field(default_factory=list)
    gap_strategies: list[GapStrategyItem] = Field(default_factory=list)
    prompt_version: str | None = None
    model: str | None = None
    generated_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
