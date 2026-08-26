"""LLM provider interface.

Every AI-driven feature (extraction, matching) goes through this interface
rather than calling a vendor SDK directly. That keeps a second provider
(e.g. OpenAI, a local model) to a single new file, and keeps prompts/schemas/
retry/trace-logging behaviour consistent regardless of vendor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.domain.ai_trace import AITrace
from app.domain.enums import AIOperationType

T = TypeVar("T", bound=BaseModel)


class StructuredLLMResult(BaseModel, Generic[T]):
    """What a provider call returns: the validated output plus its trace.

    The trace is always returned - even on failure the caller gets an
    AITrace describing what happened, via LLMProviderError.trace.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    output: T
    trace: AITrace


class LLMProviderError(Exception):
    """Raised when a structured generation could not be completed.

    Carries the AITrace so the caller can still persist an audit record for
    the failed operation.
    """

    def __init__(self, message: str, trace: AITrace) -> None:
        super().__init__(message)
        self.trace = trace


class LLMProvider(ABC):
    """Abstract interface all LLM providers implement."""

    @abstractmethod
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
        """Run one structured-output LLM call and return a validated result.

        Implementations MUST:
        - validate the model's output against `output_schema` before returning
        - retry on recoverable failures (validation errors, transient
          provider errors) up to a configured limit
        - never raise on the *first* validation failure without retrying
        - return/attach an AITrace for both success and failure paths
        """
        raise NotImplementedError
