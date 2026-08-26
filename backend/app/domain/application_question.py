"""Domain model for the application-question assistant.

Salary and work-rights questions are answered deterministically from the
candidate's own stored preferences when available (see
app/services/application_question_service.py) rather than via the LLM -
those are facts the profile already has, not something to generate.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.application_workspace import GenerationMeta
from app.domain.enums import QuestionType


class ApplicationQuestionResponse(BaseModel):
    id: UUID | None = None
    workspace_id: UUID
    question_text: str
    classifications: list[QuestionType] = Field(default_factory=list)
    answered_deterministically: bool = False
    response_text: str
    source_evidence_ids: list[UUID] = Field(default_factory=list)
    source_research_claim_ids: list[UUID] = Field(default_factory=list)
    meta: GenerationMeta
    created_at: datetime | None = None
