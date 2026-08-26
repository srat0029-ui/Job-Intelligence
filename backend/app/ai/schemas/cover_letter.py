"""Structured output contract for cover-letter generation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMCoverLetterOutput(BaseModel):
    body: str = Field(description="The full cover letter body text.")
    evidence_ids_used: list[str] = Field(default_factory=list)
    research_claim_ids_used: list[str] = Field(default_factory=list)
