"""Cover-letter generation.

Grounded entirely in the already-decided `ApplicationStrategy` plus the same
bounded evidence/research-claim lists every other generator uses - never a
fresh, unconstrained "write a cover letter for this person" instruction.
Never submitted or emailed - drafting aid only.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.prompts import cover_letter_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.cover_letter import LLMCoverLetterOutput
from app.domain.ai_trace import AITrace
from app.domain.application_strategy import ApplicationStrategy
from app.domain.application_workspace import GenerationMeta
from app.domain.candidate import Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.cover_letter import CoverLetter
from app.domain.enums import AIOperationType, GenerationStatus
from app.domain.job import ExtractedJob
from app.domain.research import ResearchClaim


class CoverLetterService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def generate(
        self,
        *,
        workspace_id: UUID,
        extracted_job: ExtractedJob,
        strategy: ApplicationStrategy,
        evidence: list[Evidence],
        research_claims: list[ResearchClaim],
        style: CommunicationStyle,
        input_identifier: str,
    ) -> tuple[CoverLetter, AITrace]:
        allowed_evidence_ids = {str(e.id) for e in evidence if e.id is not None}
        allowed_claim_ids = {str(c.id) for c in research_claims if c.id is not None}

        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.COVER_LETTER,
            prompt_version=cover_letter_v1.PROMPT_VERSION,
            system_prompt=cover_letter_v1.SYSTEM_PROMPT,
            user_prompt=cover_letter_v1.build_user_prompt(
                job_title=extracted_job.title,
                company=extracted_job.company,
                strategy=strategy,
                evidence=evidence,
                research_claims=research_claims,
                style=style,
            ),
            output_schema=LLMCoverLetterOutput,
            input_identifier=input_identifier,
        )
        output = result.output
        letter = CoverLetter(
            workspace_id=workspace_id,
            body=output.body,
            source_evidence_ids=[
                UUID(i) for i in output.evidence_ids_used if i in allowed_evidence_ids
            ],
            source_research_claim_ids=[
                UUID(i) for i in output.research_claim_ids_used if i in allowed_claim_ids
            ],
            meta=GenerationMeta(
                status=GenerationStatus.DRAFT.value,
                prompt_version=result.trace.prompt_version,
                model=result.trace.model,
                input_tokens=result.trace.input_tokens,
                output_tokens=result.trace.output_tokens,
                estimated_cost_usd=result.trace.estimated_cost_usd,
            ),
        )
        return letter, result.trace
