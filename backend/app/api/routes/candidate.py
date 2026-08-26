"""Candidate profile endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_candidate_service, get_db
from app.domain.candidate import Candidate
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidate", tags=["candidate"])


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
