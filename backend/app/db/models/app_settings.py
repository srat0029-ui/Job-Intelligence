"""ORM model for runtime-editable discovery/cost-control settings.

Modelled as a single-row table (the app enforces exactly one row) rather
than a key-value store, since the full set of settings is small, fixed, and
typed - see app/services/app_settings_service.py for how the singleton row
is created lazily on first read.
"""

from sqlalchemy import Boolean, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class AppSettingsModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "app_settings"

    auto_ai_analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_ai_analyses_per_run: Mapped[int] = mapped_column(Integer, default=20)
    daily_ai_analysis_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
