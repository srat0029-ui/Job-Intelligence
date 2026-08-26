"""Job-specific CV tailoring suggestions, with a real grounding-validation
step - not just an instruction to the model.

The candidate's existing Project/WorkExperience/Skill records (see
app/domain/candidate.py) already ARE the canonical CV representation; this
service never creates a second CV document, only proposes reworded
`suggested_text` for an existing bullet alongside its `original_text` and
the evidence that grounds it.

`_validate_suggestion` is the concrete check the milestone brief asked for:
after generation, every suggestion is scanned for
- evidence ids outside the whitelist offered to the model,
- an `original_text` that doesn't match anything actually in the
  candidate's profile,
- a number/percentage in `suggested_text` that doesn't appear anywhere in
  `original_text` or the cited evidence statements (an invented metric),
- a known technology keyword in `suggested_text` that doesn't appear in
  `original_text` or the cited evidence (an invented technology).
A suggestion that fails any of these is still returned (not silently
dropped) but marked `passed_grounding_check=False` with concrete
`grounding_issues`, so the workspace UI can surface exactly what to
distrust rather than hiding a rejected suggestion.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.prompts import cv_tailoring_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.cv_tailoring import LLMCVTailoringOutput
from app.domain.ai_trace import AITrace
from app.domain.application_workspace import GenerationMeta
from app.domain.candidate import Candidate, Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.cv_tailoring import CVBulletSuggestion, CVTailoringBatch
from app.domain.enums import AIOperationType, GenerationStatus
from app.services.grounding_checks import find_invented_metrics, find_invented_technologies


def _known_original_texts(candidate: Candidate) -> set[str]:
    texts: set[str] = set()
    for p in candidate.projects:
        texts.add(p.description)
        texts.update(p.highlights)
    for w in candidate.work_history:
        if w.summary:
            texts.add(w.summary)
    return texts


class CVTailoringService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def generate(
        self,
        *,
        workspace_id: UUID,
        job_title: str,
        company: str,
        candidate: Candidate,
        evidence: list[Evidence],
        style: CommunicationStyle,
        input_identifier: str,
    ) -> tuple[CVTailoringBatch, AITrace]:
        allowed_evidence_ids = {str(e.id) for e in evidence if e.id is not None}
        evidence_by_id = {str(e.id): e for e in evidence if e.id is not None}
        known_originals = _known_original_texts(candidate)

        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.CV_TAILORING,
            prompt_version=cv_tailoring_v1.PROMPT_VERSION,
            system_prompt=cv_tailoring_v1.SYSTEM_PROMPT,
            user_prompt=cv_tailoring_v1.build_user_prompt(
                job_title=job_title,
                company=company,
                projects=candidate.projects,
                work_history=candidate.work_history,
                skills=candidate.skills,
                evidence=evidence,
                style=style,
            ),
            output_schema=LLMCVTailoringOutput,
            input_identifier=input_identifier,
        )

        suggestions: list[CVBulletSuggestion] = []
        for item in result.output.suggestions:
            valid_evidence_ids = [
                eid for eid in item.supporting_evidence_ids if eid in allowed_evidence_ids
            ]
            grounded_text = " ".join(
                [item.original_text]
                + [evidence_by_id[eid].statement for eid in valid_evidence_ids]
            )
            issues: list[str] = []
            if len(valid_evidence_ids) != len(item.supporting_evidence_ids):
                issues.append("cited evidence outside the offered evidence set was dropped")
            if item.original_text not in known_originals:
                issues.append("original_text does not match any existing candidate profile text")
            invented_metrics = find_invented_metrics(item.suggested_text, grounded_text)
            if invented_metrics:
                issues.append(f"invented_metric: {', '.join(invented_metrics)}")
            invented_tech = find_invented_technologies(item.suggested_text, grounded_text)
            if invented_tech:
                issues.append(f"invented_technology: {', '.join(invented_tech)}")

            suggestions.append(
                CVBulletSuggestion(
                    section=item.section,
                    source_ref_label=item.source_ref_label,
                    original_text=item.original_text,
                    suggested_text=item.suggested_text,
                    relevance_rank=item.relevance_rank,
                    supporting_evidence_ids=[UUID(i) for i in valid_evidence_ids],
                    passed_grounding_check=not issues,
                    grounding_issues=issues,
                )
            )

        batch = CVTailoringBatch(
            workspace_id=workspace_id,
            suggestions=suggestions,
            section_emphasis=result.output.section_emphasis,
            source_evidence_ids=[UUID(i) for i in allowed_evidence_ids],
            meta=GenerationMeta(
                status=GenerationStatus.DRAFT.value,
                prompt_version=result.trace.prompt_version,
                model=result.trace.model,
                input_tokens=result.trace.input_tokens,
                output_tokens=result.trace.output_tokens,
                estimated_cost_usd=result.trace.estimated_cost_usd,
            ),
        )
        return batch, result.trace
