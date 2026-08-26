"""Thin CRUD for the candidate's communication-style preferences."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.communication_style import CommunicationStyle
from app.repositories.communication_style_repository import CommunicationStyleRepository


class CommunicationStyleService:
    def __init__(self, repository: CommunicationStyleRepository | None = None) -> None:
        self._repository = repository or CommunicationStyleRepository()

    def get(self, db: Session) -> CommunicationStyle:
        return self._repository.get(db)

    def update(self, db: Session, style: CommunicationStyle) -> CommunicationStyle:
        return self._repository.update(db, style)
