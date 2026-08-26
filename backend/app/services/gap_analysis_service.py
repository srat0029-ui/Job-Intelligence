"""Application-focused gap analysis.

`classify_coverage` is entirely deterministic, derived from an already-
computed `MatchResult` - it never calls the LLM and never re-decides
`is_gap` (that stays owned by `matching_service._is_gap`). Only genuine
gaps get an LLM call (`gap_strategy_v1`), and only to decide HOW to frame
the gap - never to manufacture evidence that closes it. If there are no
genuine gaps, no LLM call is made at all.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.prompts import gap_strategy_v1
from app.ai.providers.base import LLMProvider, LLMProviderError
from app.ai.schemas.gap_strategy import LLMGapStrategyOutput
from app.core.logging import get_logger
from app.domain.ai_trace import AITrace
from app.domain.candidate import Evidence
from app.domain.enums import AIOperationType, EvidenceStrength, GapStrategyCategory
from app.domain.gap_analysis import GapStrategyItem, RequirementCoverage
from app.domain.matching import MatchResult

logger = get_logger(__name__)


def classify_coverage(match_result: MatchResult) -> list[RequirementCoverage]:
    coverage: list[RequirementCoverage] = []
    for match in match_result.matches:
        if match.is_gap:
            strength = EvidenceStrength.GAP
        elif match.tier.value == "explicit":
            strength = EvidenceStrength.STRONG
        elif match.tier.value == "transferable":
            strength = EvidenceStrength.PARTIAL
        else:
            strength = EvidenceStrength.WEAK
        coverage.append(
            RequirementCoverage(
                requirement_name=match.requirement_name,
                importance=match.importance,
                strength=strength,
            )
        )
    return coverage


class GapAnalysisService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def analyze(
        self,
        *,
        match_result: MatchResult,
        evidence: list[Evidence],
        input_identifier: str,
    ) -> tuple[list[RequirementCoverage], list[GapStrategyItem], AITrace | None]:
        coverage = classify_coverage(match_result)
        gap_names = [c.requirement_name for c in coverage if c.strength == EvidenceStrength.GAP]

        if not gap_names:
            return coverage, [], None

        allowed_evidence_ids = {str(e.id) for e in evidence if e.id is not None}
        try:
            result = self._llm_provider.generate_structured(
                operation_type=AIOperationType.GAP_ANALYSIS,
                prompt_version=gap_strategy_v1.PROMPT_VERSION,
                system_prompt=gap_strategy_v1.SYSTEM_PROMPT,
                user_prompt=gap_strategy_v1.build_user_prompt(
                    gap_requirement_names=gap_names, evidence=evidence
                ),
                output_schema=LLMGapStrategyOutput,
                input_identifier=input_identifier,
            )
        except LLMProviderError as exc:
            logger.error("gap_strategy_failed", error=str(exc))
            raise

        strategies: list[GapStrategyItem] = []
        returned_names = {item.requirement_name for item in result.output.items}
        for item in result.output.items:
            valid_ids = [eid for eid in item.adjacent_evidence_ids if eid in allowed_evidence_ids]
            strategies.append(
                GapStrategyItem(
                    requirement_name=item.requirement_name,
                    strategy_category=item.strategy_category,
                    guidance=item.guidance,
                    adjacent_evidence_ids=[UUID(eid) for eid in valid_ids],
                )
            )
        # Any gap the model silently dropped still gets an honest, safe default.
        for name in gap_names:
            if name not in returned_names:
                strategies.append(
                    GapStrategyItem(
                        requirement_name=name,
                        strategy_category=GapStrategyCategory.ACKNOWLEDGE_HONESTLY,
                        guidance="No adjacent evidence identified - address honestly if raised.",
                    )
                )

        return coverage, strategies, result.trace
