"""Business logic for search profiles (thin - mostly delegates to the
repository; exists so routes never touch the ORM directly, matching the
pattern used by CandidateService/JobService)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.discovery import SearchProfile
from app.repositories.search_profile_repository import SearchProfileRepository


class SearchProfileService:
    def __init__(self, repository: SearchProfileRepository | None = None) -> None:
        self._repository = repository or SearchProfileRepository()

    def create(self, db: Session, profile: SearchProfile) -> SearchProfile:
        return self._repository.create(db, profile)

    def update(self, db: Session, profile_id: UUID, profile: SearchProfile) -> SearchProfile | None:
        return self._repository.update(db, profile_id, profile)

    def delete(self, db: Session, profile_id: UUID) -> bool:
        return self._repository.delete(db, profile_id)

    def get(self, db: Session, profile_id: UUID) -> SearchProfile | None:
        return self._repository.get(db, profile_id)

    def list_all(self, db: Session) -> list[SearchProfile]:
        return self._repository.list_all(db)

    def list_enabled(self, db: Session) -> list[SearchProfile]:
        return self._repository.list_enabled(db)
