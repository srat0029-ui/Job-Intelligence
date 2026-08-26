"""Candidate profile endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.ai.providers.base import LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.api.deps import get_candidate_service, get_db
from app.domain.candidate import Candidate
from app.ingestion.candidate_document_source import ResumeFileSource
from app.ingestion.pdf_text import UnreadablePdfError
from app.repositories.ai_trace_repository import AITraceRepository
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidate", tags=["candidate"])

MAX_CV_SIZE_BYTES = 5 * 1024 * 1024


@router.get("", response_model=Candidate | None)
def get_candidate(
    db: Session = Depends(get_db), service: CandidateService = Depends(get_candidate_service)
) -> Candidate | None:
    return service.get_profile(db)


@router.put("", response_model=Candidate)
def put_candidate(
    candidate: Candidate,
    db: Session = Depends(get_db),
    service: CandidateService = Depends(get_candidate_service),
) -> Candidate:
    if not candidate.name.strip():
        raise HTTPException(status_code=422, detail="Candidate name is required.")
    return service.save_profile(db, candidate)


@router.post("/cv/parse", response_model=Candidate)
def parse_cv(
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    file: UploadFile = File(...),
) -> Candidate:
    """Parses an uploaded PDF resume into a Candidate-shaped proposal.

    Deliberately does NOT write to the database - the response is a
    proposal for the user to review on the Profile page and selectively
    merge in before hitting "Save profile" (PUT /api/candidate), so existing
    manually-curated profile data is never silently overwritten.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF resumes are supported.")

    data = file.file.read()
    if len(data) > MAX_CV_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5MB).")

    source = ResumeFileSource(
        pdf_bytes=data, filename=file.filename or "resume.pdf", llm_provider=llm_provider
    )
    try:
        candidate, trace = source.load()
    except UnreadablePdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if trace is not None:
        AITraceRepository().save(db, trace)

    return candidate
