"""The one genuine agentic workflow in this project: Application
Intelligence preparation.

Explicit, separately-testable steps with bounded responsibility - chosen
over an orchestration framework (LangGraph etc.) because every step here is
a single, sequential, non-branching LLM call plus deterministic
post-processing; there is no parallel fan-out, no dynamic re-planning, and
no multi-agent negotiation this project actually needs. Introducing a graph
framework would add real complexity (a new dependency, a new execution
model to reason about and debug) for zero behavioural benefit at this
project's scale - the existing plain-Python-services pattern already used
by `AnalysisOrchestrator`/`DiscoveryService` is the right tool here too. See
the README's "Agentic workflow" section for the full write-up of this
decision.

Steps, each with a clear input/output schema and independent failure
handling:

    Research -> Evidence Retrieval -> Gap Analysis -> Application Strategy
    -> (on explicit request) Content Generation -> Grounding Review

`prepare_strategy` runs the first four steps in sequence - each one's
result is persisted before the next begins, so a failure partway through
(e.g. the LLM errors during strategy synthesis) still leaves the earlier
steps' output (research, gap analysis) intact and inspectable rather than
losing everything. Content generation (CV tailoring / cover letter /
question answering) is deliberately NOT run automatically as part of this
chain - each requires its own explicit trigger (Part 17: explicit user
initiation only) - but every one of them still runs through the same
GroundingReviewerService afterward, with bounded regeneration
(`MAX_REGENERATION_ATTEMPTS`, see grounding_reviewer_service.py) folded into
one logical "generate" call rather than becoming separate stored versions.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.providers.base import LLMProvider
from app.domain.application_question import ApplicationQuestionResponse
from app.domain.application_strategy import ApplicationStrategy
from app.domain.cover_letter import CoverLetter
from app.domain.cv_tailoring import CVTailoringBatch
from app.domain.enums import GenerationStatus, ReviewVerdict
from app.domain.gap_analysis import GapAnalysis
from app.ingestion.research_provider import ResearchProvider
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.application_question_repository import ApplicationQuestionRepository
from app.repositories.application_strategy_repository import ApplicationStrategyRepository
from app.repositories.application_workspace_repository import ApplicationWorkspaceRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.communication_style_repository import CommunicationStyleRepository
from app.repositories.cover_letter_repository import CoverLetterRepository
from app.repositories.cv_tailoring_repository import CVTailoringRepository
from app.repositories.gap_analysis_repository import GapAnalysisRepository
from app.repositories.job_repository import JobRepository
from app.repositories.research_repository import ResearchRepository
from app.services.application_question_service import ApplicationQuestionService
from app.services.application_strategy_service import ApplicationStrategyService
from app.services.company_research_service import CompanyResearchService, citable_claims
from app.services.cost_guard import check_daily_budget_or_raise
from app.services.cover_letter_service import CoverLetterService
from app.services.cv_tailoring_service import CVTailoringService
from app.services.evidence_retrieval_service import rank_evidence_for_job
from app.services.gap_analysis_service import GapAnalysisService
from app.services.grounding_reviewer_service import (
    MAX_REGENERATION_ATTEMPTS,
    GroundingReviewerService,
)
from app.services.priority_service import classify_priority


class WorkspaceNotFoundError(Exception):
    pass


class JobNotAnalysedError(Exception):
    pass


class ApplicationWorkflowService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        research_provider: ResearchProvider,
        *,
        workspace_repository: ApplicationWorkspaceRepository | None = None,
        job_repository: JobRepository | None = None,
        analysis_repository: AnalysisRepository | None = None,
        candidate_repository: CandidateRepository | None = None,
        research_repository: ResearchRepository | None = None,
        gap_analysis_repository: GapAnalysisRepository | None = None,
        strategy_repository: ApplicationStrategyRepository | None = None,
        cv_repository: CVTailoringRepository | None = None,
        question_repository: ApplicationQuestionRepository | None = None,
        cover_letter_repository: CoverLetterRepository | None = None,
        style_repository: CommunicationStyleRepository | None = None,
        ai_trace_repository: AITraceRepository | None = None,
    ) -> None:
        self._workspace_repository = workspace_repository or ApplicationWorkspaceRepository()
        self._job_repository = job_repository or JobRepository()
        self._analysis_repository = analysis_repository or AnalysisRepository()
        self._candidate_repository = candidate_repository or CandidateRepository()
        self._research_repository = research_repository or ResearchRepository()
        self._gap_analysis_repository = gap_analysis_repository or GapAnalysisRepository()
        self._strategy_repository = strategy_repository or ApplicationStrategyRepository()
        self._cv_repository = cv_repository or CVTailoringRepository()
        self._question_repository = question_repository or ApplicationQuestionRepository()
        self._cover_letter_repository = cover_letter_repository or CoverLetterRepository()
        self._style_repository = style_repository or CommunicationStyleRepository()
        self._ai_trace_repository = ai_trace_repository or AITraceRepository()

        self._research_service = CompanyResearchService(
            llm_provider, research_provider, self._research_repository, self._ai_trace_repository
        )
        self._gap_service = GapAnalysisService(llm_provider)
        self._strategy_service = ApplicationStrategyService(llm_provider)
        self._cv_service = CVTailoringService(llm_provider)
        self._question_service = ApplicationQuestionService(llm_provider)
        self._cover_letter_service = CoverLetterService(llm_provider)
        self._reviewer_service = GroundingReviewerService(llm_provider)

    def _load_job_context(self, db, workspace_id: UUID):
        workspace = self._workspace_repository.get(db, workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(f"Workspace {workspace_id} not found")
        job = self._job_repository.get(db, workspace.job_id)
        analysis = self._analysis_repository.get_latest_for_job(db, workspace.job_id)
        if job is None or analysis is None:
            raise JobNotAnalysedError(
                "This job has not been analysed yet - run analysis before preparing an application."
            )
        candidate = self._candidate_repository.get_singleton(db)
        style = self._style_repository.get(db)
        return workspace, job, analysis, candidate, style

    def add_research_source(
        self, db, workspace_id: UUID, *, url: str, source_type, force_refresh: bool = False
    ):
        check_daily_budget_or_raise(db)
        workspace, job, _analysis, _candidate, _style = self._load_job_context(db, workspace_id)
        company_name = workspace.research_company_name or job.company
        if workspace.research_company_name is None:
            self._workspace_repository.set_research_company_name(db, workspace_id, company_name)
        return self._research_service.add_source_and_research(
            db,
            company_name=company_name,
            url=url,
            source_type=source_type,
            force_refresh=force_refresh,
        )

    def prepare_strategy(self, db, workspace_id: UUID) -> ApplicationStrategy:
        """Runs Evidence Retrieval -> Gap Analysis -> Application Strategy,
        reusing whatever company research is already cached for this job's
        company (research itself is added separately via
        `add_research_source`, since it needs a URL supplied by the user)."""
        check_daily_budget_or_raise(db)
        workspace, job, analysis, candidate, style = self._load_job_context(db, workspace_id)

        company_name = workspace.research_company_name or job.company
        bundle = self._research_service.get_bundle(db, company_name)
        research_claims = citable_claims(bundle.claims)

        evidence = rank_evidence_for_job(
            candidate=candidate,
            extracted_job=analysis.extracted_job,
            match_result=analysis.match_result,
        )

        gap_input_id = f"workspace:{workspace_id}:gap_analysis"
        coverage, gap_strategies, gap_trace = self._gap_service.analyze(
            match_result=analysis.match_result, evidence=evidence, input_identifier=gap_input_id
        )
        if gap_trace is not None:
            self._ai_trace_repository.save(db, gap_trace)
        gap_analysis = self._gap_analysis_repository.save(
            db,
            GapAnalysis(
                workspace_id=workspace_id,
                job_analysis_id=analysis.id,
                coverage=coverage,
                gap_strategies=gap_strategies,
                prompt_version=gap_trace.prompt_version if gap_trace else None,
                model=gap_trace.model if gap_trace else None,
                input_tokens=gap_trace.input_tokens if gap_trace else None,
                output_tokens=gap_trace.output_tokens if gap_trace else None,
                estimated_cost_usd=gap_trace.estimated_cost_usd if gap_trace else None,
            ),
        )

        assert gap_analysis.id is not None  # always set post-save
        strategy_input_id = f"workspace:{workspace_id}:application_strategy"
        strategy, strategy_trace = self._strategy_service.build(
            workspace_id=workspace_id,
            gap_analysis_id=gap_analysis.id,
            extracted_job=analysis.extracted_job,
            evidence=evidence,
            research_claims=research_claims,
            gap_strategies=gap_strategies,
            style=style,
            recommendation=analysis.fit_score.recommendation.value,
            application_priority=classify_priority(analysis.fit_score.overall_score).value,
            input_identifier=strategy_input_id,
        )
        self._ai_trace_repository.save(db, strategy_trace)
        return self._strategy_repository.save(db, strategy)

    def generate_cv_tailoring(self, db, workspace_id: UUID) -> CVTailoringBatch:
        check_daily_budget_or_raise(db)
        workspace, job, analysis, candidate, style = self._load_job_context(db, workspace_id)
        evidence = rank_evidence_for_job(
            candidate=candidate,
            extracted_job=analysis.extracted_job,
            match_result=analysis.match_result,
        )

        batch = None
        for attempt in range(1, MAX_REGENERATION_ATTEMPTS + 2):
            batch, trace = self._cv_service.generate(
                workspace_id=workspace_id,
                job_title=analysis.extracted_job.title,
                company=analysis.extracted_job.company,
                candidate=candidate,
                evidence=evidence,
                style=style,
                input_identifier=f"workspace:{workspace_id}:cv_tailoring",
            )
            self._ai_trace_repository.save(db, trace)
            batch.meta.regeneration_attempt = attempt

            combined_text = "\n".join(s.suggested_text for s in batch.suggestions)
            review, review_trace = self._reviewer_service.review(
                content_type="cv_tailoring",
                generated_text=combined_text,
                job_title=analysis.extracted_job.title,
                company=analysis.extracted_job.company,
                evidence=evidence,
                research_claims=[],
                input_identifier=f"workspace:{workspace_id}:cv_tailoring:review",
            )
            self._ai_trace_repository.save(db, review_trace)
            batch.meta.reviewer_result = review.verdict.value
            batch.meta.reviewer_issues = [i.description for i in review.issues]
            batch.meta.status = (
                GenerationStatus.REVIEWED.value
                if review.verdict != ReviewVerdict.FAIL
                else GenerationStatus.NEEDS_REVIEW.value
            )
            if review.verdict != ReviewVerdict.FAIL:
                break

        assert batch is not None  # the loop always runs at least once
        return self._cv_repository.save(db, batch)

    def generate_cover_letter(self, db, workspace_id: UUID) -> CoverLetter:
        check_daily_budget_or_raise(db)
        workspace, job, analysis, candidate, style = self._load_job_context(db, workspace_id)
        strategy = self._strategy_repository.get_latest(db, workspace_id)
        if strategy is None:
            raise JobNotAnalysedError(
                "No application strategy yet - generate a strategy before drafting a cover letter."
            )
        company_name = workspace.research_company_name or job.company
        research_claims = citable_claims(
            self._research_service.get_bundle(db, company_name).claims
        )
        evidence = rank_evidence_for_job(
            candidate=candidate,
            extracted_job=analysis.extracted_job,
            match_result=analysis.match_result,
        )

        letter = None
        for attempt in range(1, MAX_REGENERATION_ATTEMPTS + 2):
            letter, trace = self._cover_letter_service.generate(
                workspace_id=workspace_id,
                extracted_job=analysis.extracted_job,
                strategy=strategy,
                evidence=evidence,
                research_claims=research_claims,
                style=style,
                input_identifier=f"workspace:{workspace_id}:cover_letter",
            )
            self._ai_trace_repository.save(db, trace)
            letter.meta.regeneration_attempt = attempt

            review, review_trace = self._reviewer_service.review(
                content_type="cover_letter",
                generated_text=letter.body,
                job_title=analysis.extracted_job.title,
                company=analysis.extracted_job.company,
                evidence=evidence,
                research_claims=research_claims,
                input_identifier=f"workspace:{workspace_id}:cover_letter:review",
            )
            self._ai_trace_repository.save(db, review_trace)
            letter.meta.reviewer_result = review.verdict.value
            letter.meta.reviewer_issues = [i.description for i in review.issues]
            letter.meta.status = (
                GenerationStatus.REVIEWED.value
                if review.verdict != ReviewVerdict.FAIL
                else GenerationStatus.NEEDS_REVIEW.value
            )
            if review.verdict != ReviewVerdict.FAIL:
                break

        assert letter is not None  # the loop always runs at least once
        return self._cover_letter_repository.save(db, letter)

    def answer_question(
        self, db, workspace_id: UUID, question_text: str
    ) -> ApplicationQuestionResponse:
        check_daily_budget_or_raise(db)
        workspace, job, analysis, candidate, style = self._load_job_context(db, workspace_id)
        company_name = workspace.research_company_name or job.company
        research_claims = citable_claims(
            self._research_service.get_bundle(db, company_name).claims
        )
        evidence = rank_evidence_for_job(
            candidate=candidate,
            extracted_job=analysis.extracted_job,
            match_result=analysis.match_result,
        )

        response, trace = self._question_service.answer(
            workspace_id=workspace_id,
            question_text=question_text,
            job_title=analysis.extracted_job.title,
            company=analysis.extracted_job.company,
            candidate=candidate,
            evidence=evidence,
            research_claims=research_claims,
            style=style,
            input_identifier=f"workspace:{workspace_id}:application_question",
        )
        if trace is not None:
            self._ai_trace_repository.save(db, trace)

        if not response.answered_deterministically:
            review, review_trace = self._reviewer_service.review(
                content_type="application_question",
                generated_text=response.response_text,
                job_title=analysis.extracted_job.title,
                company=analysis.extracted_job.company,
                evidence=evidence,
                research_claims=research_claims,
                input_identifier=f"workspace:{workspace_id}:application_question:review",
            )
            self._ai_trace_repository.save(db, review_trace)
            response.meta.reviewer_result = review.verdict.value
            response.meta.reviewer_issues = [i.description for i in review.issues]
            response.meta.status = (
                GenerationStatus.REVIEWED.value
                if review.verdict != ReviewVerdict.FAIL
                else GenerationStatus.NEEDS_REVIEW.value
            )

        return self._question_repository.save(db, response)
