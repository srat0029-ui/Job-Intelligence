"""Business logic for the candidate profile (thin - mostly delegates to the
repository; exists so routes never touch the DB session/ORM directly and so
future validation rules (e.g. "at least one evidence item per skill") have
an obvious home)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.candidate import Candidate
from app.repositories.candidate_repository import CandidateRepository


class CandidateService:
    def __init__(self, repository: CandidateRepository | None = None) -> None:
        self._repository = repository or CandidateRepository()

    def get_profile(self, db: Session) -> Candidate | None:
        return self._repository.get_singleton(db)

    def save_profile(self, db: Session, candidate: Candidate) -> Candidate:
        return self._repository.upsert(db, candidate)
