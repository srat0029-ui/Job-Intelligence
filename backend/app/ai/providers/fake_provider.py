"""Deterministic fake provider - no network calls.

Used by the test suite (so unit/integration tests don't need an Anthropic
API key) and as a local-dev fallback when ANTHROPIC_API_KEY is unset, so the
app is still explorable without secrets configured. Callers register a
canned response per operation_type; if none is registered it raises, making
misuse obvious rather than silently returning nonsense.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.ai.providers.base import LLMProvider, StructuredLLMResult
from app.domain.ai_trace import AITrace
from app.domain.enums import AIOperationType, AITraceStatus

T = TypeVar("T", bound=BaseModel)


class FakeLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self._responses: dict[AIOperationType, BaseModel] = {}

    def set_response(self, operation_type: AIOperationType, response: BaseModel) -> None:
        self._responses[operation_type] = response

    def generate_structured(
        self,
        *,
        operation_type: AIOperationType,
        prompt_version: str,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        input_identifier: str,
    ) -> StructuredLLMResult[T]:
        canned = self._responses.get(operation_type)
        if canned is None:
            raise RuntimeError(
                f"FakeLLMProvider has no canned response registered for {operation_type}"
            )
        validated = output_schema.model_validate(canned.model_dump(mode="json"))
        trace = AITrace(
            operation_type=operation_type,
            prompt_version=prompt_version,
            model="fake-provider",
            input_identifier=input_identifier,
            status=AITraceStatus.SUCCESS,
            latency_ms=1,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            attempt_number=1,
        )
        return StructuredLLMResult(output=validated, trace=trace)
