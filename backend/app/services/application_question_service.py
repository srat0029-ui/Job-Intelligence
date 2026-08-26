"""Application-question classification and response generation.

Classification is entirely deterministic (keyword matching against a fixed
vocabulary per QuestionType) - reliable and auditable, the same "not
everything needs an LLM call" discipline already used for location/
work-rights matching in `app/services/matching_service.py`. Salary and
work-rights questions are answered directly from the candidate's stored
`CandidatePreferences` when that data exists, bypassing the LLM entirely
(zero cost, zero hallucination risk for a fact the profile already has) -
only falling through to LLM generation when deterministic data can't answer
the question.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.prompts import application_question_v1
from app.ai.providers.base import LLMProvider
from app.ai.schemas.application_question import LLMApplicationQuestionOutput
from app.domain.ai_trace import AITrace
from app.domain.application_question import ApplicationQuestionResponse
from app.domain.application_workspace import GenerationMeta
from app.domain.candidate import Candidate, Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.enums import AIOperationType, GenerationStatus, QuestionType
from app.domain.research import ResearchClaim

_CLASSIFICATION_KEYWORDS: dict[QuestionType, list[str]] = {
    QuestionType.SALARY: ["salary", "remuneration", "pay", "compensation", "expected pay"],
    QuestionType.WORK_RIGHTS: [
        "work rights", "visa", "sponsorship", "right to work", "citizen", "permanent resident",
    ],
    QuestionType.COMPANY_MOTIVATION: ["why do you want to work", "why this company", "why us"],
    QuestionType.MOTIVATION: ["why are you interested", "what motivates you", "why this role"],
    QuestionType.TEAMWORK: ["team", "collaborat", "work with others"],
    QuestionType.LEADERSHIP: ["lead a team", "leadership", "mentor"],
    QuestionType.PROBLEM_SOLVING: ["problem", "challenge you faced", "difficult situation"],
    QuestionType.LEARNING: ["learn a new", "picked up", "learning quickly", "unfamiliar"],
    QuestionType.PROJECT_EXPERIENCE: ["describe a project", "tell us about a project"],
    QuestionType.TECHNICAL_EXPERIENCE: [
        "experience with", "technical experience", "describe your experience working with",
    ],
    QuestionType.BEHAVIOURAL: [
        "describe a time", "give an example of a time", "tell me about a time",
    ],
    QuestionType.VALUES: ["our values", "company values", "culture fit"],
}  # fmt: skip


def classify_question(question_text: str) -> list[QuestionType]:
    lowered = question_text.lower()
    matched = [
        qtype
        for qtype, keywords in _CLASSIFICATION_KEYWORDS.items()
        if any(kw in lowered for kw in keywords)
    ]
    return matched or [QuestionType.GENERAL_BACKGROUND]


def _try_deterministic_answer(
    classifications: list[QuestionType], candidate: Candidate
) -> str | None:
    prefs = candidate.preferences
    if QuestionType.SALARY in classifications:
        if prefs.salary_expectation_min or prefs.salary_expectation_max:
            lo, hi = prefs.salary_expectation_min, prefs.salary_expectation_max
            if lo and hi:
                return f"My salary expectation is {lo}-{hi} {prefs.salary_currency} per year."
            amount = lo or hi
            return f"My salary expectation is around {amount} {prefs.salary_currency} per year."
        return None
    if QuestionType.WORK_RIGHTS in classifications:
        if prefs.work_rights:
            return f"My work rights: {', '.join(prefs.work_rights)}."
        return None
    return None


class ApplicationQuestionService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    def answer(
        self,
        *,
        workspace_id: UUID,
        question_text: str,
        job_title: str,
        company: str,
        candidate: Candidate,
        evidence: list[Evidence],
        research_claims: list[ResearchClaim],
        style: CommunicationStyle,
        input_identifier: str,
    ) -> tuple[ApplicationQuestionResponse, AITrace | None]:
        classifications = classify_question(question_text)

        deterministic_answer = _try_deterministic_answer(classifications, candidate)
        if deterministic_answer is not None:
            response = ApplicationQuestionResponse(
                workspace_id=workspace_id,
                question_text=question_text,
                classifications=classifications,
                answered_deterministically=True,
                response_text=deterministic_answer,
                meta=GenerationMeta(
                    status=GenerationStatus.REVIEWED.value,  # deterministic - nothing to review
                    prompt_version="deterministic_profile_lookup_v1",
                    model="none",
                ),
            )
            return response, None

        allowed_evidence_ids = {str(e.id) for e in evidence if e.id is not None}
        allowed_claim_ids = {str(c.id) for c in research_claims if c.id is not None}

        result = self._llm_provider.generate_structured(
            operation_type=AIOperationType.APPLICATION_QUESTION,
            prompt_version=application_question_v1.PROMPT_VERSION,
            system_prompt=application_question_v1.SYSTEM_PROMPT,
            user_prompt=application_question_v1.build_user_prompt(
                question_text=question_text,
                classifications=[c.value for c in classifications],
                job_title=job_title,
                company=company,
                evidence=evidence,
                research_claims=research_claims,
                style=style,
            ),
            output_schema=LLMApplicationQuestionOutput,
            input_identifier=input_identifier,
        )
        output = result.output
        response = ApplicationQuestionResponse(
            workspace_id=workspace_id,
            question_text=question_text,
            classifications=classifications,
            answered_deterministically=False,
            response_text=output.response_text,
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
        return response, result.trace
