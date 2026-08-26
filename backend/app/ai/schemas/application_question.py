"""Structured output contract for application-question response generation.

Classification happens deterministically in code
(`app/services/application_question_service.py::classify_question`), not via
the LLM - this schema only covers grounded response generation once a
question is already classified and its evidence/research context assembled.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMApplicationQuestionOutput(BaseModel):
    response_text: str = Field(description="A concise, honest, first-person draft answer.")
    evidence_ids_used: list[str] = Field(default_factory=list)
    research_claim_ids_used: list[str] = Field(default_factory=list)
