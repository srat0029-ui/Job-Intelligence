"""Business logic for the runtime discovery/cost-control settings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.app_settings import AppSettings
from app.repositories.app_settings_repository import AppSettingsRepository


class AppSettingsService:
    def __init__(self, repository: AppSettingsRepository | None = None) -> None:
        self._repository = repository or AppSettingsRepository()

    def get(self, db: Session) -> AppSettings:
        return self._repository.get(db)

    def update(self, db: Session, settings: AppSettings) -> AppSettings:
        return self._repository.update(db, settings)
