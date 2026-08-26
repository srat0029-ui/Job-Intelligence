"""Anthropic Claude implementation of LLMProvider.

Uses forced tool-use to get schema-constrained JSON out of the model
(the model's only "tool" is `emit_result`, and `tool_choice` forces it to
call it), then validates the tool input against the requested Pydantic
schema. Retries on validation failures and transient provider errors up to
`settings.llm_max_retries`, logging one AITrace per attempt.
"""

from __future__ import annotations

import time
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.ai.providers.base import LLMProvider, LLMProviderError, StructuredLLMResult
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.ai_trace import AITrace
from app.domain.enums import AIOperationType, AITraceStatus

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

RESULT_TOOL_NAME = "emit_result"


MAX_BACKOFF_SECONDS = 8.0


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(
            api_key=api_key or settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
        )
        self._model = model or settings.anthropic_model
        self._max_retries = settings.llm_max_retries
        self._input_cost = settings.llm_input_cost_per_million
        self._output_cost = settings.llm_output_cost_per_million

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
        schema = output_schema.model_json_schema()
        # Pydantic emits $defs/$ref for nested models; Anthropic's tool
        # input_schema accepts standard JSON Schema so this passes through.
        tool = {
            "name": RESULT_TOOL_NAME,
            "description": f"Emit the structured result for {operation_type.value}.",
            "input_schema": schema,
        }

        last_error: Exception | None = None
        last_trace: AITrace | None = None

        for attempt in range(1, self._max_retries + 2):  # first try + retries
            start = time.perf_counter()
            try:
                # The tool/tool_choice dicts are built from plain JSON schema,
                # not the SDK's TypedDict builders, so mypy can't verify their
                # shape against the overloaded signature - verified at runtime
                # by the Anthropic client instead.
                response = self._client.messages.create(  # type: ignore[call-overload]
                    model=self._model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    tools=[tool],
                    tool_choice={"type": "tool", "name": RESULT_TOOL_NAME},
                )
            except anthropic.APIError as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                last_trace = AITrace(
                    operation_type=operation_type,
                    prompt_version=prompt_version,
                    model=self._model,
                    input_identifier=input_identifier,
                    status=AITraceStatus.PROVIDER_ERROR,
                    latency_ms=latency_ms,
                    error_message=str(exc),
                    attempt_number=attempt,
                )
                last_error = exc
                logger.warning("llm_provider_error", attempt=attempt, error=str(exc))
                self._sleep_before_retry(attempt, exc)
                continue

            latency_ms = int((time.perf_counter() - start) * 1000)
            input_tokens = getattr(response.usage, "input_tokens", None)
            output_tokens = getattr(response.usage, "output_tokens", None)
            estimated_cost = self._estimate_cost(input_tokens, output_tokens)

            tool_use_block = next(
                (block for block in response.content if block.type == "tool_use"), None
            )
            if tool_use_block is None:
                last_trace = AITrace(
                    operation_type=operation_type,
                    prompt_version=prompt_version,
                    model=self._model,
                    input_identifier=input_identifier,
                    status=AITraceStatus.VALIDATION_FAILED,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimated_cost,
                    error_message="Model did not return a tool_use block.",
                    attempt_number=attempt,
                )
                last_error = ValueError("no tool_use block in response")
                continue

            try:
                validated = output_schema.model_validate(tool_use_block.input)
            except ValidationError as exc:
                last_trace = AITrace(
                    operation_type=operation_type,
                    prompt_version=prompt_version,
                    model=self._model,
                    input_identifier=input_identifier,
                    status=AITraceStatus.VALIDATION_FAILED,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimated_cost,
                    error_message=str(exc)[:2000],
                    attempt_number=attempt,
                )
                last_error = exc
                logger.warning("llm_validation_failed", attempt=attempt, error=str(exc)[:500])
                continue

            status = AITraceStatus.SUCCESS if attempt == 1 else AITraceStatus.RETRIED_SUCCESS
            trace = AITrace(
                operation_type=operation_type,
                prompt_version=prompt_version,
                model=self._model,
                input_identifier=input_identifier,
                status=status,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
                attempt_number=attempt,
            )
            return StructuredLLMResult(output=validated, trace=trace)

        assert last_trace is not None
        attempts = self._max_retries + 1
        raise LLMProviderError(
            f"LLM structured generation failed after {attempts} attempts: {last_error}",
            trace=last_trace,
        )

    def _sleep_before_retry(self, attempt: int, exc: Exception) -> None:
        """Bounded exponential backoff before a provider-error retry.

        Never sleeps more than MAX_BACKOFF_SECONDS regardless of attempt
        count - `_max_retries` already bounds the number of attempts, this
        just avoids hammering a rate-limited/overloaded API immediately.
        """
        base = 2.0 if isinstance(exc, anthropic.RateLimitError) else 0.5
        delay = min(base * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
        time.sleep(delay)

    def _estimate_cost(self, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if input_tokens is None or output_tokens is None:
            return None
        return round(
            (input_tokens / 1_000_000) * self._input_cost
            + (output_tokens / 1_000_000) * self._output_cost,
            6,
        )
