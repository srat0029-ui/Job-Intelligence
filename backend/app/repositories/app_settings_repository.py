"""Data access for the singleton runtime settings row.

Lazily creates the row on first read/write - there's no seed/migration step
that needs to run first, and a fresh database should behave identically to
one with defaults explicitly saved.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.app_settings import AppSettingsModel
from app.domain.app_settings import AppSettings


def _to_domain(model: AppSettingsModel) -> AppSettings:
    return AppSettings(
        auto_ai_analysis_enabled=model.auto_ai_analysis_enabled,
        max_ai_analyses_per_run=model.max_ai_analyses_per_run,
        daily_ai_analysis_budget_usd=model.daily_ai_analysis_budget_usd,
    )


class AppSettingsRepository:
    def _get_or_create_model(self, db: Session) -> AppSettingsModel:
        model = db.query(AppSettingsModel).first()
        if model is None:
            model = AppSettingsModel()
            db.add(model)
            db.commit()
            db.refresh(model)
        return model

    def get(self, db: Session) -> AppSettings:
        return _to_domain(self._get_or_create_model(db))

    def update(self, db: Session, settings: AppSettings) -> AppSettings:
        model = self._get_or_create_model(db)
        model.auto_ai_analysis_enabled = settings.auto_ai_analysis_enabled
        model.max_ai_analyses_per_run = settings.max_ai_analyses_per_run
        model.daily_ai_analysis_budget_usd = settings.daily_ai_analysis_budget_usd
        db.commit()
        db.refresh(model)
        return _to_domain(model)
