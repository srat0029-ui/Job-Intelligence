"""Matches extracted job requirements against candidate evidence.

Design summary (the anti-hallucination guarantee the spec asks for):
1. Most requirement categories (skills, technologies, education, experience,
   domain knowledge, soft skills) are matched by asking the LLM to classify
   an evidence tier for each requirement, but the LLM may only cite
   `evidence_id`s from the fixed candidate evidence list we hand it in the
   prompt.
2. This code NEVER trusts that constraint on the model's word alone: any
   evidence_id the model returns that isn't in the allowed set is silently
   dropped before the match is built, and if that leaves zero evidence for a
   claimed non-"no_evidence" tier, the tier is force-downgraded. The LLM
   cannot cause the system to assert experience that isn't on file.
3. `is_gap` is never taken from the model - it's derived in code from tier +
   importance (see `_is_gap`).
4. Location and work-rights are handled without any LLM call at all: they're
   plain deterministic comparisons against the candidate's stored
   preferences, because "do I have a working visa" isn't a fuzzy evidence-
   matching problem.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.prompts import matching_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.matching import LLMMatchingOutput
from app.domain.ai_trace import AITrace
from app.domain.candidate import Candidate
from app.domain.enums import (
    AIOperationType,
    EvidenceTier,
    RequirementCategory,
    RequirementImportance,
)
from app.domain.job import ExtractedRequirement
from app.domain.matching import MatchResult, RequirementMatch

LLM_MATCHED_CATEGORIES = {
    RequirementCategory.TECHNICAL_SKILL,
    RequirementCategory.TECHNOLOGY,
    RequirementCategory.EDUCATION,
    RequirementCategory.EXPERIENCE,
    RequirementCategory.DOMAIN_KNOWLEDGE,
    RequirementCategory.SOFT_SKILL,
}
DETERMINISTIC_CATEGORIES = {RequirementCategory.LOCATION, RequirementCategory.WORK_RIGHTS}


def _is_gap(tier: EvidenceTier, importance: RequirementImportance) -> bool:
    """A required item is a gap unless there's at least transferable
    evidence; a preferred item is only a gap if there's genuinely nothing."""
    if importance == RequirementImportance.REQUIRED:
        return tier in (EvidenceTier.WEAK_INFERENCE, EvidenceTier.NO_EVIDENCE)
    return tier == EvidenceTier.NO_EVIDENCE


def _match_deterministic(
    requirement: ExtractedRequirement, candidate: Candidate
) -> RequirementMatch:
    prefs = candidate.preferences
    haystack = " ".join(prefs.work_rights + prefs.preferred_locations).lower()
    tokens = [t for t in requirement.name.lower().split() if len(t) > 2]
    hit = any(token in haystack for token in tokens) if tokens else False
    tier = EvidenceTier.EXPLICIT if hit else EvidenceTier.NO_EVIDENCE
    summary = (
        f"Matches your stated {requirement.category.value.replace('_', ' ')} preferences."
        if hit
        else f"No stated preference covers '{requirement.raw_phrase}'."
    )
    return RequirementMatch(
        requirement_name=requirement.name,
        category=requirement.category,
        importance=requirement.importance,
        tier=tier,
        confidence=1.0,
        evidence_ids=[],
        evidence_summary=summary,
        is_gap=_is_gap(tier, requirement.importance),
    )


class MatchingService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def match(
        self,
        *,
        requirements: list[ExtractedRequirement],
        candidate: Candidate,
        input_identifier: str,
    ) -> tuple[MatchResult, AITrace | None]:
        llm_requirements = [r for r in requirements if r.category in LLM_MATCHED_CATEGORIES]
        deterministic_requirements = [
            r for r in requirements if r.category in DETERMINISTIC_CATEGORIES
        ]

        deterministic_matches = {
            r.name: _match_deterministic(r, candidate) for r in deterministic_requirements
        }

        llm_matches: dict[str, RequirementMatch] = {}
        trace: AITrace | None = None
        if llm_requirements:
            llm_matches, trace = self._match_via_llm(llm_requirements, candidate, input_identifier)

        ordered: list[RequirementMatch] = []
        for r in requirements:
            if r.name in llm_matches:
                ordered.append(llm_matches[r.name])
            elif r.name in deterministic_matches:
                ordered.append(deterministic_matches[r.name])
            # else: requirement had no evidence category handling (shouldn't
            # happen given the two sets above are exhaustive over the enum)

        return MatchResult(matches=ordered), trace

    def _match_via_llm(
        self, requirements: list[ExtractedRequirement], candidate: Candidate, input_identifier: str
    ) -> tuple[dict[str, RequirementMatch], AITrace]:
        allowed_evidence_ids = {str(e.id) for e in candidate.evidence if e.id is not None}

        user_prompt = matching_v1.build_user_prompt(
            requirements=requirements, evidence=candidate.evidence
        )
        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.REQUIREMENT_MATCHING,
            prompt_version=matching_v1.PROMPT_VERSION,
            system_prompt=matching_v1.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=LLMMatchingOutput,
            input_identifier=input_identifier,
        )
        llm_output: LLMMatchingOutput = result.output

        requirement_by_name = {r.name: r for r in requirements}
        matches: dict[str, RequirementMatch] = {}
        for item in llm_output.matches:
            requirement = requirement_by_name.get(item.requirement_name)
            if requirement is None:
                continue  # model echoed a name we didn't ask about - ignore it

            # Enforce the evidence whitelist regardless of what the model claims.
            valid_ids = [eid for eid in item.evidence_ids if eid in allowed_evidence_ids]
            tier = item.tier
            if tier != EvidenceTier.NO_EVIDENCE and not valid_ids:
                tier = EvidenceTier.NO_EVIDENCE

            matches[requirement.name] = RequirementMatch(
                requirement_name=requirement.name,
                category=requirement.category,
                importance=requirement.importance,
                tier=tier,
                confidence=item.confidence,
                evidence_ids=[UUID(eid) for eid in valid_ids],
                evidence_summary=item.evidence_summary,
                is_gap=_is_gap(tier, requirement.importance),
            )

        # Any requirement the model silently dropped becomes an explicit gap
        # rather than disappearing from the analysis.
        for requirement in requirements:
            if requirement.name not in matches:
                matches[requirement.name] = RequirementMatch(
                    requirement_name=requirement.name,
                    category=requirement.category,
                    importance=requirement.importance,
                    tier=EvidenceTier.NO_EVIDENCE,
                    confidence=0.0,
                    evidence_ids=[],
                    evidence_summary="Model did not return a classification for this requirement.",
                    is_gap=_is_gap(EvidenceTier.NO_EVIDENCE, requirement.importance),
                )

        return matches, result.trace
