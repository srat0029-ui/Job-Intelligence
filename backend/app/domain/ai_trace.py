"""Domain model for the AI operation audit trail.

Every call to an LLMProvider produces one of these. Deliberately excludes any
hidden chain-of-thought: only concise, application-relevant outputs plus
operational metadata (latency, tokens, cost, status) are stored.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import AIOperationType, AITraceStatus


class AITrace(BaseModel):
    id: UUID | None = None
    operation_type: AIOperationType
    prompt_version: str
    model: str
    input_identifier: str  # e.g. job_id, so a trace can be tied back to what it operated on
    status: AITraceStatus
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error_message: str | None = None
    attempt_number: int = 1
    created_at: datetime | None = None
