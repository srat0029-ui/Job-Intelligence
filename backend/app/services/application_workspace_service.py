"""Application Workspace CRUD and the Overview aggregation.

The workspace is associated with the existing `Job`/`JobAnalysis` records,
not a second job system - `get_or_create` keys entirely off `job_id`.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.domain.application_brief import ApplicationBrief
from app.domain.application_workspace import ApplicationWorkspace
from app.domain.candidate import Evidence
from app.domain.job import Job
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.application_question_repository import ApplicationQuestionRepository
from app.repositories.application_strategy_repository import ApplicationStrategyRepository
from app.repositories.application_workspace_repository import ApplicationWorkspaceRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.cover_letter_repository import CoverLetterRepository
from app.repositories.cv_tailoring_repository import CVTailoringRepository
from app.repositories.gap_analysis_repository import GapAnalysisRepository
from app.repositories.job_repository import JobRepository
from app.repositories.research_repository import ResearchRepository
from app.services.application_brief_service import build_brief


class WorkspaceOverview(BaseModel):
    workspace: ApplicationWorkspace
    job: Job
    overall_score: float | None
    recommendation: str | None
    application_status: str | None
    strongest_evidence_labels: list[str]
    main_gaps: list[str]
    research_source_count: int
    research_claim_count: int
    has_strategy: bool
    has_cv_tailoring: bool
    has_cover_letter: bool
    question_count: int
    brief: ApplicationBrief | None


class ApplicationWorkspaceService:
    def __init__(
        self,
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

    def get_or_create_for_job(self, db, job_id: UUID) -> ApplicationWorkspace:
        return self._workspace_repository.get_or_create(db, job_id)

    def update_notes(self, db, workspace_id: UUID, notes: str) -> ApplicationWorkspace | None:
        return self._workspace_repository.update_notes(db, workspace_id, notes)

    def get_overview(self, db, workspace_id: UUID) -> WorkspaceOverview | None:
        workspace = self._workspace_repository.get(db, workspace_id)
        if workspace is None:
            return None
        job = self._job_repository.get(db, workspace.job_id)
        if job is None:
            # workspace.job_id is a real FK to jobs.id (CASCADE) - this
            # would only happen mid-transaction, never in practice.
            return None
        analysis = self._analysis_repository.get_latest_for_job(db, workspace.job_id)

        strongest_labels: list[str] = []
        main_gaps: list[str] = []
        if analysis is not None:
            candidate = self._candidate_repository.get_singleton(db)
            evidence_by_id: dict[str, Evidence] = (
                {str(e.id): e for e in candidate.evidence if e.id is not None}
                if candidate
                else {}
            )
            for match in analysis.match_result.matches:
                if match.tier.value == "explicit" and not match.is_gap:
                    for eid in match.evidence_ids:
                        ev = evidence_by_id.get(str(eid))
                        if ev and ev.source_label not in strongest_labels:
                            strongest_labels.append(ev.source_label)
                if match.is_gap:
                    main_gaps.append(match.requirement_name)

        company_name = workspace.research_company_name or (job.company if job else "")
        sources = self._research_repository.list_sources_for_company(db, company_name)
        claims = self._research_repository.list_claims_for_company(db, company_name)

        strategy = self._strategy_repository.get_latest(db, workspace_id)
        cv_batch = self._cv_repository.get_latest(db, workspace_id)
        cover_letter = self._cover_letter_repository.get_latest(db, workspace_id)
        questions = self._question_repository.list_all_for_workspace(db, workspace_id)

        brief = None
        if analysis is not None and strategy is not None:
            gap_analysis = self._gap_analysis_repository.get(db, strategy.gap_analysis_id)
            candidate = self._candidate_repository.get_singleton(db)
            evidence_by_id = (
                {str(e.id): e for e in candidate.evidence if e.id is not None}
                if candidate
                else {}
            )
            if gap_analysis is not None:
                brief = build_brief(
                    analysis=analysis,
                    strategy=strategy,
                    gap_analysis=gap_analysis,
                    evidence_by_id=evidence_by_id,
                    research_claims=claims,
                )

        return WorkspaceOverview(
            workspace=workspace,
            job=job,
            overall_score=analysis.fit_score.overall_score if analysis else None,
            recommendation=analysis.fit_score.recommendation.value if analysis else None,
            application_status=(
                job.application_status.value if job and job.application_status else None
            ),
            strongest_evidence_labels=strongest_labels[:4],
            main_gaps=main_gaps,
            research_source_count=len(sources),
            research_claim_count=len(claims),
            has_strategy=strategy is not None,
            has_cv_tailoring=cv_batch is not None,
            has_cover_letter=cover_letter is not None,
            question_count=len(questions),
            brief=brief,
        )
