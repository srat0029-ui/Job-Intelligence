"""Dedicated grounding-review stage for generated application content.

Two layers, code always wins over the model:
1. Deterministic structural checks (`grounding_checks.py`) - invented
   metrics/technologies in the free text against the same evidence/research
   the content was allowed to cite. Any hit is an automatic FAIL regardless
   of what the LLM reviewer below concludes.
2. An LLM review pass (`grounding_review_v1`) covering the fuzzier
   judgement calls a regex can't make: overstated transferable experience,
   stale research presented as current, requirement coverage, writing
   quality. This is a genuinely separate model call from whatever generated
   the content - not the same call grading itself.

`MAX_REGENERATION_ATTEMPTS` bounds automatic regeneration - callers (the
application workflow) must stop and surface NEEDS_REVIEW after this many
attempts, never loop indefinitely.
"""

from __future__ import annotations

from app.ai.prompts import grounding_review_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.grounding_review import LLMGroundingReviewOutput
from app.domain.ai_trace import AITrace
from app.domain.candidate import Evidence
from app.domain.enums import AIOperationType, ReviewVerdict
from app.domain.grounding_review import GroundingIssue, GroundingReviewResult
from app.domain.research import ResearchClaim
from app.services.grounding_checks import find_invented_metrics, find_invented_technologies

MAX_REGENERATION_ATTEMPTS = 2


class GroundingReviewerService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def review(
        self,
        *,
        content_type: str,
        generated_text: str,
        job_title: str,
        company: str,
        evidence: list[Evidence],
        research_claims: list[ResearchClaim],
        input_identifier: str,
    ) -> tuple[GroundingReviewResult, AITrace]:
        grounded_text = " ".join(
            [e.statement for e in evidence] + [c.claim for c in research_claims]
        )
        code_issues: list[GroundingIssue] = []

        invented_metrics = find_invented_metrics(generated_text, grounded_text)
        if invented_metrics:
            code_issues.append(
                GroundingIssue(
                    category="candidate_grounding",
                    severity="fail",
                    description=f"Number(s) not present in provided evidence/research: "
                    f"{', '.join(invented_metrics)}",
                )
            )
        invented_tech = find_invented_technologies(generated_text, grounded_text)
        if invented_tech:
            code_issues.append(
                GroundingIssue(
                    category="candidate_grounding",
                    severity="fail",
                    description=f"Technology mentioned but not present in provided evidence: "
                    f"{', '.join(invented_tech)}",
                )
            )
        code_level_fail = any(i.severity == "fail" for i in code_issues)

        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.GROUNDING_REVIEW,
            prompt_version=grounding_review_v1.PROMPT_VERSION,
            system_prompt=grounding_review_v1.SYSTEM_PROMPT,
            user_prompt=grounding_review_v1.build_user_prompt(
                content_type=content_type,
                generated_text=generated_text,
                job_title=job_title,
                company=company,
                evidence=evidence,
                research_claims=research_claims,
            ),
            output_schema=LLMGroundingReviewOutput,
            input_identifier=input_identifier,
        )
        llm_issues = [
            GroundingIssue(category=i.category, severity=i.severity, description=i.description)
            for i in result.output.issues
        ]
        all_issues = code_issues + llm_issues

        if code_level_fail or any(i.severity == "fail" for i in llm_issues):
            verdict = ReviewVerdict.FAIL
        elif all_issues:
            verdict = ReviewVerdict.PASS_WITH_WARNINGS
        else:
            verdict = ReviewVerdict.PASS

        return GroundingReviewResult(verdict=verdict, issues=all_issues), result.trace
