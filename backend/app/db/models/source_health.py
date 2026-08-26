"""ORM model for per-source health tracking (see app/domain/source_health.py)."""

from datetime import datetime

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class SourceHealthModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "source_health"

    source_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error_category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jobs_retrieved_last_run: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
