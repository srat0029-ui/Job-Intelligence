"""Data access for the singleton runtime settings row.

Lazily creates the row on first read/write - there's no seed/migration step
that needs to run first, and a fresh database should behave identically to
one with defaults explicitly saved.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models.app_settings import AppSettingsModel
from app.domain.app_settings import AppSettings


def _to_domain(model: AppSettingsModel) -> AppSettings:
    return AppSettings(
        auto_ai_analysis_enabled=model.auto_ai_analysis_enabled,
        max_ai_analyses_per_run=model.max_ai_analyses_per_run,
        daily_ai_analysis_budget_usd=model.daily_ai_analysis_budget_usd,
        auto_discovery_enabled=model.auto_discovery_enabled,
        discovery_frequency_hours=model.discovery_frequency_hours,
        max_postings_per_source_per_run=model.max_postings_per_source_per_run,
        last_scheduled_run_at=model.last_scheduled_run_at,
        next_scheduled_run_at=model.next_scheduled_run_at,
        gmail_sync_frequency_minutes=model.gmail_sync_frequency_minutes,
        next_gmail_sync_at=model.next_gmail_sync_at,
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
        model.auto_discovery_enabled = settings.auto_discovery_enabled
        model.discovery_frequency_hours = settings.discovery_frequency_hours
        model.max_postings_per_source_per_run = settings.max_postings_per_source_per_run
        model.gmail_sync_frequency_minutes = settings.gmail_sync_frequency_minutes
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def set_schedule_timestamps(
        self,
        db: Session,
        *,
        last_scheduled_run_at: datetime | None = None,
        next_scheduled_run_at: datetime | None = None,
    ) -> AppSettings:
        model = self._get_or_create_model(db)
        if last_scheduled_run_at is not None:
            model.last_scheduled_run_at = last_scheduled_run_at
        if next_scheduled_run_at is not None:
            model.next_scheduled_run_at = next_scheduled_run_at
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def set_next_gmail_sync_at(self, db: Session, next_gmail_sync_at: datetime) -> AppSettings:
        model = self._get_or_create_model(db)
        model.next_gmail_sync_at = next_gmail_sync_at
        db.commit()
        db.refresh(model)
        return _to_domain(model)
