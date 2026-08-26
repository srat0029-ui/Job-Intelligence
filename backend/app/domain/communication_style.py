"""Domain model for the candidate's application writing-style preferences.

A single editable, DB-backed settings row (same pattern as `AppSettings`),
so tone/style is configurable rather than hard-coded into prompts, and
never tied to one hard-coded name. This layer only ever constrains *how*
generated text reads - it must never be allowed to relax grounding rules
(no invented facts/evidence), which are enforced entirely in code
independently of style.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommunicationStyle(BaseModel):
    tone: str = Field(
        default="conversational_professional",
        description="One of: concise, natural, conversational_professional.",
    )
    avoid_buzzwords: bool = True
    avoid_exaggerated_claims: bool = True
    prefer_specific_examples: bool = True
    avoid_em_dashes: bool = True
    region_convention: str = "australian"
