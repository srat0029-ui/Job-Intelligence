"""Orchestrates a full job analysis: extraction -> matching -> scoring.

This is the one workflow the whole product hinges on, so it's kept as its
own small coordinator rather than folded into a route handler or another
service - each step's AITrace is persisted regardless of whether the
overall workflow ultimately succeeds, so the audit trail survives partial
failures too.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.providers.base import LLMProvider, LLMProviderError
from app.core.logging import get_logger
from app.domain.analysis import JobAnalysis
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.job_repository import JobRepository
from app.services.extraction_service import ExtractionService
from app.services.matching_service import MatchingService
from app.services.scoring_service import ScoringService

logger = get_logger(__name__)


class JobNotFoundError(Exception):
    pass


class CandidateProfileMissingError(Exception):
    pass


class AnalysisOrchestrator:
    def __init__(
        self,
        llm_provider: LLMProvider,
        job_repository: JobRepository | None = None,
        candidate_repository: CandidateRepository | None = None,
        analysis_repository: AnalysisRepository | None = None,
        ai_trace_repository: AITraceRepository | None = None,
    ) -> None:
        self._extraction_service = ExtractionService(llm_provider)
        self._matching_service = MatchingService(llm_provider)
        self._scoring_service = ScoringService()
        self._job_repository = job_repository or JobRepository()
        self._candidate_repository = candidate_repository or CandidateRepository()
        self._analysis_repository = analysis_repository or AnalysisRepository()
        self._ai_trace_repository = ai_trace_repository or AITraceRepository()

    def analyze(self, db: Session, job_id: UUID) -> JobAnalysis:
        job = self._job_repository.get(db, job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")

        candidate = self._candidate_repository.get_singleton(db)
        if candidate is None:
            raise CandidateProfileMissingError(
                "No candidate profile exists yet - seed or create one before analysing jobs."
            )

        try:
            extracted_job, extraction_trace = self._extraction_service.extract(job)
        except LLMProviderError as exc:
            self._ai_trace_repository.save(db, exc.trace)
            logger.error("job_extraction_failed", job_id=str(job_id), error=str(exc))
            raise
        self._ai_trace_repository.save(db, extraction_trace)

        try:
            match_result, matching_trace = self._matching_service.match(
                requirements=extracted_job.requirements,
                candidate=candidate,
                input_identifier=str(job_id),
            )
        except LLMProviderError as exc:
            self._ai_trace_repository.save(db, exc.trace)
            logger.error("requirement_matching_failed", job_id=str(job_id), error=str(exc))
            raise
        if matching_trace is not None:
            self._ai_trace_repository.save(db, matching_trace)

        fit_score = self._scoring_service.score(
            extracted_job=extracted_job, match_result=match_result, candidate=candidate
        )

        return self._analysis_repository.save(
            db,
            job_id=job_id,
            extracted_job=extracted_job,
            match_result=match_result,
            fit_score=fit_score,
        )
