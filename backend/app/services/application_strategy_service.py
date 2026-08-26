"""Synthesises the ApplicationStrategy artefact.

`application_priority`/`recommendation` are copied straight from the
already-computed FitScore/JobPriority passed in - this service never asks
the LLM for a number and never recomputes one. Every evidence/research
claim the model is allowed to cite is passed in as a fixed, bounded list;
`lead_evidence_ids` returned by the model is whitelisted against that list
before being trusted, exactly like MatchingService's evidence_ids.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.prompts import application_strategy_v1
from app.ai.providers.base import LLMProvider, LLMProviderError
from app.ai.schemas.application_strategy import LLMApplicationStrategyOutput
from app.domain.ai_trace import AITrace
from app.domain.application_strategy import ApplicationStrategy, ConcernItem
from app.domain.application_workspace import GenerationMeta
from app.domain.candidate import Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.enums import AIOperationType, GenerationStatus
from app.domain.gap_analysis import GapStrategyItem
from app.domain.job import ExtractedJob
from app.domain.research import ResearchClaim


class ApplicationStrategyService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def build(
        self,
        *,
        workspace_id: UUID,
        gap_analysis_id: UUID,
        extracted_job: ExtractedJob,
        evidence: list[Evidence],
        research_claims: list[ResearchClaim],
        gap_strategies: list[GapStrategyItem],
        style: CommunicationStyle,
        recommendation: str,
        application_priority: str | None,
        input_identifier: str,
    ) -> tuple[ApplicationStrategy, AITrace]:
        allowed_evidence_ids = {str(e.id) for e in evidence if e.id is not None}
        allowed_claim_ids = {str(c.id) for c in research_claims if c.id is not None}

        try:
            result = self._llm_provider.generate_structured(
                operation_type=AIOperationType.APPLICATION_STRATEGY,
                prompt_version=application_strategy_v1.PROMPT_VERSION,
                system_prompt=application_strategy_v1.SYSTEM_PROMPT,
                user_prompt=application_strategy_v1.build_user_prompt(
                    job_title=extracted_job.title,
                    company=extracted_job.company,
                    role_category=extracted_job.role_category,
                    responsibilities=extracted_job.responsibilities,
                    evidence=evidence,
                    research_claims=research_claims,
                    gap_strategies=gap_strategies,
                    style=style,
                ),
                output_schema=LLMApplicationStrategyOutput,
                input_identifier=input_identifier,
            )
        except LLMProviderError:
            raise

        output = result.output
        lead_ids = [UUID(i) for i in output.lead_evidence_ids if i in allowed_evidence_ids]

        strategy = ApplicationStrategy(
            workspace_id=workspace_id,
            gap_analysis_id=gap_analysis_id,
            positioning=output.positioning,
            lead_evidence_ids=lead_ids,
            skills_to_emphasise=output.skills_to_emphasise,
            skills_to_deemphasise=output.skills_to_deemphasise,
            likely_concerns=[
                ConcernItem(concern=c.concern, response_strategy=c.response_strategy)
                for c in output.likely_concerns
            ],
            motivation_themes=output.motivation_themes,
            application_priority=application_priority,
            recommendation=recommendation,
            source_evidence_ids=[UUID(i) for i in allowed_evidence_ids],
            source_research_claim_ids=[UUID(i) for i in allowed_claim_ids],
            meta=GenerationMeta(
                status=GenerationStatus.DRAFT.value,
                prompt_version=result.trace.prompt_version,
                model=result.trace.model,
                input_tokens=result.trace.input_tokens,
                output_tokens=result.trace.output_tokens,
                estimated_cost_usd=result.trace.estimated_cost_usd,
            ),
        )
        return strategy, result.trace
