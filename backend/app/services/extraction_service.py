"""Converts a raw job posting into validated structured data via the LLM.

This is the only place a raw job description string is handed to an LLM.
Everything downstream (matching, scoring, the API, the UI) reads from the
typed `ExtractedJob` this returns - never from `raw_description` again.
"""

from __future__ import annotations

from app.ai.prompts import extraction_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.extraction import ExtractedJob
from app.domain.ai_trace import AITrace
from app.domain.enums import AIOperationType
from app.domain.job import Job


class ExtractionService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def extract(self, job: Job) -> tuple[ExtractedJob, AITrace]:
        user_prompt = extraction_v1.build_user_prompt(
            raw_description=job.raw_description,
            title=job.title,
            company=job.company,
            location=job.location,
        )
        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.JOB_EXTRACTION,
            prompt_version=extraction_v1.PROMPT_VERSION,
            system_prompt=extraction_v1.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=ExtractedJob,
            input_identifier=str(job.id),
        )
        return result.output, result.trace
