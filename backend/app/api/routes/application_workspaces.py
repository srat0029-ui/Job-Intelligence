"""Application Workspace endpoints (Milestone 4A - Application Intelligence).

Two routers: one extra route on the existing job-scoped path
(`POST /api/jobs/{job_id}/workspace` - the entry point from an analysed
job), and the main `/api/application-workspaces/{workspace_id}/...` router
for everything that happens once a workspace exists. A third,
`/api/communication-style`, is candidate-wide (not workspace-scoped).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_application_workflow_service,
    get_application_workspace_service,
    get_communication_style_service,
    get_db,
)
from app.api.schemas import (
    AddResearchSourceRequest,
    SubmitQuestionRequest,
    UpdateWorkspaceNotesRequest,
)
from app.domain.application_brief import ApplicationBrief
from app.domain.application_question import ApplicationQuestionResponse
from app.domain.application_strategy import ApplicationStrategy
from app.domain.application_workspace import ApplicationWorkspace
from app.domain.communication_style import CommunicationStyle
from app.domain.cover_letter import CoverLetter
from app.domain.cv_tailoring import CVTailoringBatch
from app.domain.research import CompanyResearchBundle, ResearchSource
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.application_question_repository import ApplicationQuestionRepository
from app.repositories.application_strategy_repository import ApplicationStrategyRepository
from app.repositories.cover_letter_repository import CoverLetterRepository
from app.repositories.cv_tailoring_repository import CVTailoringRepository
from app.repositories.research_repository import ResearchRepository
from app.services.application_workflow_service import (
    ApplicationWorkflowService,
    JobNotAnalysedError,
    WorkspaceNotFoundError,
)
from app.services.application_workspace_service import (
    ApplicationWorkspaceService,
    WorkspaceOverview,
)
from app.services.communication_style_service import CommunicationStyleService
from app.services.cost_guard import DailyBudgetExceededError

jobs_router = APIRouter(prefix="/api/jobs", tags=["application-workspaces"])
router = APIRouter(prefix="/api/application-workspaces", tags=["application-workspaces"])
style_router = APIRouter(prefix="/api/communication-style", tags=["application-workspaces"])

_WORKFLOW_ERRORS = (WorkspaceNotFoundError, JobNotAnalysedError, DailyBudgetExceededError)


def _translate_workflow_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, JobNotAnalysedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DailyBudgetExceededError):
        return HTTPException(status_code=429, detail=str(exc))
    return HTTPException(status_code=500, detail="Application intelligence generation failed")


@jobs_router.post("/{job_id}/workspace", response_model=ApplicationWorkspace)
def get_or_create_workspace(
    job_id: UUID,
    db=Depends(get_db),
    service: ApplicationWorkspaceService = Depends(get_application_workspace_service),
) -> ApplicationWorkspace:
    return service.get_or_create_for_job(db, job_id)


@router.get("/{workspace_id}", response_model=WorkspaceOverview)
def get_workspace_overview(
    workspace_id: UUID,
    db=Depends(get_db),
    service: ApplicationWorkspaceService = Depends(get_application_workspace_service),
) -> WorkspaceOverview:
    overview = service.get_overview(db, workspace_id)
    if overview is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return overview


@router.put("/{workspace_id}/notes", response_model=ApplicationWorkspace)
def update_workspace_notes(
    workspace_id: UUID,
    payload: UpdateWorkspaceNotesRequest,
    db=Depends(get_db),
    service: ApplicationWorkspaceService = Depends(get_application_workspace_service),
) -> ApplicationWorkspace:
    workspace = service.update_notes(db, workspace_id, payload.notes)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.get("/{workspace_id}/brief", response_model=ApplicationBrief)
def get_application_brief(
    workspace_id: UUID,
    db=Depends(get_db),
    service: ApplicationWorkspaceService = Depends(get_application_workspace_service),
) -> ApplicationBrief:
    overview = service.get_overview(db, workspace_id)
    if overview is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if overview.brief is None:
        raise HTTPException(
            status_code=409, detail="No application strategy yet - generate one first."
        )
    return overview.brief


# --- Company research ---


@router.post("/{workspace_id}/research/sources", response_model=ResearchSource)
def add_research_source(
    workspace_id: UUID,
    payload: AddResearchSourceRequest,
    db=Depends(get_db),
    workflow: ApplicationWorkflowService = Depends(get_application_workflow_service),
) -> ResearchSource:
    try:
        return workflow.add_research_source(
            db,
            workspace_id,
            url=payload.url,
            source_type=payload.source_type,
            force_refresh=payload.force_refresh,
        )
    except _WORKFLOW_ERRORS as exc:
        raise _translate_workflow_errors(exc) from exc


@router.get("/{workspace_id}/research", response_model=CompanyResearchBundle)
def get_research_bundle(
    workspace_id: UUID,
    db=Depends(get_db),
    workspace_service: ApplicationWorkspaceService = Depends(get_application_workspace_service),
) -> CompanyResearchBundle:
    overview = workspace_service.get_overview(db, workspace_id)
    if overview is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    company_name = overview.workspace.research_company_name or overview.job.company
    repo = ResearchRepository()
    sources = repo.list_sources_for_company(db, company_name)
    claims = repo.list_claims_for_company(db, company_name)
    return CompanyResearchBundle(company_name=company_name, sources=sources, claims=claims)


# --- Application strategy ---


@router.post("/{workspace_id}/strategy", response_model=ApplicationStrategy)
def generate_strategy(
    workspace_id: UUID,
    db=Depends(get_db),
    workflow: ApplicationWorkflowService = Depends(get_application_workflow_service),
) -> ApplicationStrategy:
    try:
        return workflow.prepare_strategy(db, workspace_id)
    except _WORKFLOW_ERRORS as exc:
        raise _translate_workflow_errors(exc) from exc


@router.get("/{workspace_id}/strategy", response_model=ApplicationStrategy | None)
def get_latest_strategy(workspace_id: UUID, db=Depends(get_db)) -> ApplicationStrategy | None:
    return ApplicationStrategyRepository().get_latest(db, workspace_id)


@router.get("/{workspace_id}/strategy/history", response_model=list[ApplicationStrategy])
def get_strategy_history(workspace_id: UUID, db=Depends(get_db)) -> list[ApplicationStrategy]:
    return ApplicationStrategyRepository().list_history(db, workspace_id)


# --- CV tailoring ---


@router.post("/{workspace_id}/cv-tailoring", response_model=CVTailoringBatch)
def generate_cv_tailoring(
    workspace_id: UUID,
    db=Depends(get_db),
    workflow: ApplicationWorkflowService = Depends(get_application_workflow_service),
) -> CVTailoringBatch:
    try:
        return workflow.generate_cv_tailoring(db, workspace_id)
    except _WORKFLOW_ERRORS as exc:
        raise _translate_workflow_errors(exc) from exc


@router.get("/{workspace_id}/cv-tailoring", response_model=CVTailoringBatch | None)
def get_latest_cv_tailoring(workspace_id: UUID, db=Depends(get_db)) -> CVTailoringBatch | None:
    return CVTailoringRepository().get_latest(db, workspace_id)


@router.get("/{workspace_id}/cv-tailoring/history", response_model=list[CVTailoringBatch])
def get_cv_tailoring_history(workspace_id: UUID, db=Depends(get_db)) -> list[CVTailoringBatch]:
    return CVTailoringRepository().list_history(db, workspace_id)


# --- Application questions ---


@router.post("/{workspace_id}/questions", response_model=ApplicationQuestionResponse)
def submit_question(
    workspace_id: UUID,
    payload: SubmitQuestionRequest,
    db=Depends(get_db),
    workflow: ApplicationWorkflowService = Depends(get_application_workflow_service),
) -> ApplicationQuestionResponse:
    try:
        return workflow.answer_question(db, workspace_id, payload.question_text)
    except _WORKFLOW_ERRORS as exc:
        raise _translate_workflow_errors(exc) from exc


@router.get("/{workspace_id}/questions", response_model=list[ApplicationQuestionResponse])
def list_questions(workspace_id: UUID, db=Depends(get_db)) -> list[ApplicationQuestionResponse]:
    return ApplicationQuestionRepository().list_all_for_workspace(db, workspace_id)


@router.get("/{workspace_id}/questions/history", response_model=list[ApplicationQuestionResponse])
def get_question_history(
    workspace_id: UUID, question_text: str, db=Depends(get_db)
) -> list[ApplicationQuestionResponse]:
    return ApplicationQuestionRepository().list_history(db, workspace_id, question_text)


# --- Cover letter ---


@router.post("/{workspace_id}/cover-letter", response_model=CoverLetter)
def generate_cover_letter(
    workspace_id: UUID,
    db=Depends(get_db),
    workflow: ApplicationWorkflowService = Depends(get_application_workflow_service),
) -> CoverLetter:
    try:
        return workflow.generate_cover_letter(db, workspace_id)
    except _WORKFLOW_ERRORS as exc:
        raise _translate_workflow_errors(exc) from exc


@router.get("/{workspace_id}/cover-letter", response_model=CoverLetter | None)
def get_latest_cover_letter(workspace_id: UUID, db=Depends(get_db)) -> CoverLetter | None:
    return CoverLetterRepository().get_latest(db, workspace_id)


@router.get("/{workspace_id}/cover-letter/history", response_model=list[CoverLetter])
def get_cover_letter_history(workspace_id: UUID, db=Depends(get_db)) -> list[CoverLetter]:
    return CoverLetterRepository().list_history(db, workspace_id)


# --- Debug / traceability (Part 16) ---


@router.get("/{workspace_id}/trace")
def get_workspace_trace(workspace_id: UUID, db=Depends(get_db)) -> dict:
    """Development/debug view: every AI call tagged for this workspace,
    with prompt version, model, tokens, cost, and status - see
    app/services/application_workflow_service.py for the input_identifier
    tagging convention this relies on."""
    traces = AITraceRepository().list_for_input_prefix(db, f"workspace:{workspace_id}:")
    return {
        "workspace_id": str(workspace_id),
        "ai_calls": [
            {
                "operation_type": t.operation_type.value,
                "input_identifier": t.input_identifier,
                "prompt_version": t.prompt_version,
                "model": t.model,
                "status": t.status.value,
                "input_tokens": t.input_tokens,
                "output_tokens": t.output_tokens,
                "estimated_cost_usd": t.estimated_cost_usd,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in traces
        ],
        "total_estimated_cost_usd": sum(t.estimated_cost_usd or 0.0 for t in traces),
    }


# --- Communication style (candidate-wide, not workspace-scoped) ---


@style_router.get("", response_model=CommunicationStyle)
def get_communication_style(
    db=Depends(get_db),
    service: CommunicationStyleService = Depends(get_communication_style_service),
) -> CommunicationStyle:
    return service.get(db)


@style_router.put("", response_model=CommunicationStyle)
def update_communication_style(
    style: CommunicationStyle,
    db=Depends(get_db),
    service: CommunicationStyleService = Depends(get_communication_style_service),
) -> CommunicationStyle:
    return service.update(db, style)
