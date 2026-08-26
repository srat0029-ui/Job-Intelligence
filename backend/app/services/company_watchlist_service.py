"""Business logic for the target-company watchlist (thin - mirrors
SearchProfileService's pattern)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.company_watchlist import CompanyWatchlistEntry
from app.repositories.company_watchlist_repository import CompanyWatchlistRepository


class CompanyWatchlistService:
    def __init__(self, repository: CompanyWatchlistRepository | None = None) -> None:
        self._repository = repository or CompanyWatchlistRepository()

    def create(self, db: Session, entry: CompanyWatchlistEntry) -> CompanyWatchlistEntry:
        return self._repository.create(db, entry)

    def update(
        self, db: Session, entry_id: UUID, entry: CompanyWatchlistEntry
    ) -> CompanyWatchlistEntry | None:
        return self._repository.update(db, entry_id, entry)

    def delete(self, db: Session, entry_id: UUID) -> bool:
        return self._repository.delete(db, entry_id)

    def get(self, db: Session, entry_id: UUID) -> CompanyWatchlistEntry | None:
        return self._repository.get(db, entry_id)

    def list_all(self, db: Session) -> list[CompanyWatchlistEntry]:
        return self._repository.list_all(db)

    def list_enabled(self, db: Session) -> list[CompanyWatchlistEntry]:
        return self._repository.list_enabled(db)
