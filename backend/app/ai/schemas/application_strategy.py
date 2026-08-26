"""Structured output contract for the ApplicationStrategy artefact.

Deliberately excludes any numeric score or recommendation field - the model
never assigns application priority; `ApplicationStrategyService` copies that
straight from the already-stored FitScore/JobPriority.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMConcernItem(BaseModel):
    concern: str
    response_strategy: str = Field(description="How to honestly address this concern if raised.")


class LLMApplicationStrategyOutput(BaseModel):
    positioning: str = Field(description="1-3 sentences: the strongest honest positioning.")
    lead_evidence_ids: list[str] = Field(
        default_factory=list,
        description="2-4 evidence IDs (from the list provided) that should dominate the "
        "application - the strongest, most relevant items only.",
    )
    skills_to_emphasise: list[str] = Field(default_factory=list)
    skills_to_deemphasise: list[str] = Field(default_factory=list)
    likely_concerns: list[LLMConcernItem] = Field(
        default_factory=list,
        description="Concerns reasonably derivable from the job and profile only - do not "
        "invent concerns with no basis in the provided material.",
    )
    motivation_themes: list[str] = Field(
        default_factory=list,
        description="Genuine connections between candidate evidence, the role, and the "
        "provided company research claims only.",
    )
