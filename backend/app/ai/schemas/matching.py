"""Structured output contract for requirement matching.

Deliberately a *narrower* schema than the domain RequirementMatch: the LLM
only supplies the evidence-tier classification, a confidence score, which
candidate evidence IDs (from the fixed list it was given) support the
requirement, and a short user-facing explanation. `category`/`importance`
are NOT re-emitted by the model - MatchingService joins them back in from
the deterministic extraction output, and `is_gap` is computed in code, not
trusted from the model. This keeps the "LLM classifies, code decides" split
enforced by the schema itself, not just by convention.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import EvidenceTier


class LLMRequirementMatchItem(BaseModel):
    requirement_name: str
    tier: EvidenceTier
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="IDs selected ONLY from the candidate evidence list provided in the prompt. "
        "Never invent an ID or describe experience not present in that list.",
    )
    evidence_summary: str = Field(
        description="One short sentence, user-facing, no chain-of-thought."
    )


class LLMMatchingOutput(BaseModel):
    matches: list[LLMRequirementMatchItem] = Field(default_factory=list)
