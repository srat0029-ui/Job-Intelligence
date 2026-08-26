"""Job and analysis endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_orchestrator, get_analysis_repository, get_db, get_job_service
from app.api.schemas import CreateJobRequest
from app.domain.analysis import JobAnalysis
from app.domain.job import Job
from app.ingestion.job_source import ManualJobSource
from app.repositories.analysis_repository import AnalysisRepository
from app.services.analysis_orchestrator import (
    AnalysisOrchestrator,
    CandidateProfileMissingError,
    JobNotFoundError,
)
from app.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=Job, status_code=201)
def create_job(
    payload: CreateJobRequest,
    db: Session = Depends(get_db),
    service: JobService = Depends(get_job_service),
) -> Job:
    source = ManualJobSource(
        title=payload.title,
        company=payload.company,
        raw_description=payload.raw_description,
        location=payload.location,
        source_url=payload.source_url,
    )
    jobs = service.add_job(db, source)
    return jobs[0]


@router.get("", response_model=list[Job])
def list_jobs(
    db: Session = Depends(get_db), service: JobService = Depends(get_job_service)
) -> list[Job]:
    return service.list_jobs(db)


@router.get("/{job_id}", response_model=Job)
def get_job(
    job_id: UUID, db: Session = Depends(get_db), service: JobService = Depends(get_job_service)
) -> Job:
    job = service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/analyze", response_model=JobAnalysis)
def analyze_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    orchestrator: AnalysisOrchestrator = Depends(get_analysis_orchestrator),
) -> JobAnalysis:
    try:
        return orchestrator.analyze(db, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CandidateProfileMissingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{job_id}/analysis", response_model=JobAnalysis | None)
def get_latest_analysis(
    job_id: UUID,
    db: Session = Depends(get_db),
    repository: AnalysisRepository = Depends(get_analysis_repository),
) -> JobAnalysis | None:
    return repository.get_latest_for_job(db, job_id)
