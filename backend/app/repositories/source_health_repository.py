"""Data access for per-source health tracking.

`record_success`/`record_failure` are the only write paths - both do a
get-or-create on `source_key` so callers never need a separate
"register this source" step before its first fetch attempt.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.source_health import SourceHealthModel
from app.domain.enums import SourceHealthStatus
from app.domain.source_health import (
    CONSECUTIVE_FAILURES_FOR_DEGRADED,
    CONSECUTIVE_FAILURES_FOR_ERROR,
    SourceHealth,
)


def _to_domain(model: SourceHealthModel) -> SourceHealth:
    return SourceHealth(
        source_key=model.source_key,
        status=SourceHealthStatus(model.status),
        last_attempt_at=model.last_attempt_at,
        last_success_at=model.last_success_at,
        consecutive_failures=model.consecutive_failures,
        last_error_category=model.last_error_category,
        jobs_retrieved_last_run=model.jobs_retrieved_last_run,
        avg_latency_ms=model.avg_latency_ms,
        attempts_count=model.attempts_count,
    )


class SourceHealthRepository:
    def _get_or_create(self, db: Session, source_key: str) -> SourceHealthModel:
        model = db.execute(
            select(SourceHealthModel).where(SourceHealthModel.source_key == source_key)
        ).scalar_one_or_none()
        if model is None:
            model = SourceHealthModel(source_key=source_key)
            db.add(model)
            db.flush()
        return model

    def record_success(
        self, db: Session, source_key: str, *, jobs_retrieved: int, latency_ms: float
    ) -> SourceHealth:
        model = self._get_or_create(db, source_key)
        now = datetime.now(UTC)
        model.last_attempt_at = now
        model.last_success_at = now
        model.consecutive_failures = 0
        model.last_error_category = None
        model.jobs_retrieved_last_run = jobs_retrieved
        total_latency = (model.avg_latency_ms or 0.0) * model.attempts_count + latency_ms
        model.attempts_count += 1
        model.avg_latency_ms = total_latency / model.attempts_count
        model.status = SourceHealthStatus.HEALTHY.value
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def record_failure(self, db: Session, source_key: str, *, error_category: str) -> SourceHealth:
        model = self._get_or_create(db, source_key)
        now = datetime.now(UTC)
        model.last_attempt_at = now
        model.consecutive_failures += 1
        model.last_error_category = error_category[:200]
        model.attempts_count += 1
        if model.consecutive_failures >= CONSECUTIVE_FAILURES_FOR_ERROR:
            model.status = SourceHealthStatus.ERROR.value
        elif model.consecutive_failures >= CONSECUTIVE_FAILURES_FOR_DEGRADED:
            model.status = SourceHealthStatus.DEGRADED.value
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def get(self, db: Session, source_key: str) -> SourceHealth | None:
        model = db.execute(
            select(SourceHealthModel).where(SourceHealthModel.source_key == source_key)
        ).scalar_one_or_none()
        return _to_domain(model) if model else None

    def list_all(self, db: Session) -> list[SourceHealth]:
        models = db.execute(select(SourceHealthModel)).scalars().all()
        return [_to_domain(m) for m in models]
