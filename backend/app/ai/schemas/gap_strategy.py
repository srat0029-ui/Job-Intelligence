"""Structured output contract for per-gap application strategy.

`adjacent_evidence_ids` is whitelist-enforced in code
(`app/services/gap_analysis_service.py`) exactly like requirement matching -
the model may only cite IDs from the evidence it was actually given.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import GapStrategyCategory


class LLMGapStrategyItem(BaseModel):
    requirement_name: str
    strategy_category: GapStrategyCategory
    guidance: str = Field(
        description="One or two concise, honest sentences. Must never claim the candidate "
        "has direct experience they don't - only describe how to honestly frame the gap."
    )
    adjacent_evidence_ids: list[str] = Field(
        default_factory=list,
        description="IDs of candidate evidence (from the list provided) that are genuinely "
        "adjacent/transferable to this gap. Empty if nothing is adjacent.",
    )


class LLMGapStrategyOutput(BaseModel):
    items: list[LLMGapStrategyItem] = Field(default_factory=list)
