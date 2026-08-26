"""Data access for the discovery-run audit log."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.discovery import DiscoveryRunModel
from app.domain.discovery import DiscoveryRun, DiscoveryRunCounts
from app.domain.enums import DiscoveryRunStatus


def _to_domain(model: DiscoveryRunModel) -> DiscoveryRun:
    return DiscoveryRun(
        id=model.id,
        status=DiscoveryRunStatus(model.status),
        search_profile_ids=list(model.search_profile_ids or []),
        sources_used=list(model.sources_used or []),
        counts=DiscoveryRunCounts(
            retrieved=model.retrieved_count,
            new=model.new_count,
            duplicates=model.duplicate_count,
            prefilter_rejected=model.prefilter_rejected_count,
            eligible=model.eligible_count,
            analysed=model.analysed_count,
            deferred=model.deferred_count,
            failed=model.failed_count,
            strong_apply_or_better=model.strong_apply_or_better_count,
        ),
        estimated_cost_usd=model.estimated_cost_usd,
        error_message=model.error_message,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


class DiscoveryRunRepository:
    def start(
        self, db: Session, *, search_profile_ids: list[UUID], sources_used: list[str]
    ) -> DiscoveryRunModel:
        model = DiscoveryRunModel(
            status=DiscoveryRunStatus.RUNNING.value,
            search_profile_ids=search_profile_ids,
            sources_used=sources_used,
            started_at=datetime.now(UTC),
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return model

    def finish(
        self,
        db: Session,
        model: DiscoveryRunModel,
        *,
        counts: DiscoveryRunCounts,
        estimated_cost_usd: float,
        status: DiscoveryRunStatus,
        error_message: str | None = None,
    ) -> DiscoveryRun:
        model.retrieved_count = counts.retrieved
        model.new_count = counts.new
        model.duplicate_count = counts.duplicates
        model.prefilter_rejected_count = counts.prefilter_rejected
        model.eligible_count = counts.eligible
        model.analysed_count = counts.analysed
        model.deferred_count = counts.deferred
        model.failed_count = counts.failed
        model.strong_apply_or_better_count = counts.strong_apply_or_better
        model.estimated_cost_usd = estimated_cost_usd
        model.status = status.value
        model.error_message = error_message
        model.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def get(self, db: Session, run_id: UUID) -> DiscoveryRun | None:
        model = db.get(DiscoveryRunModel, run_id)
        return _to_domain(model) if model else None

    def list_recent(self, db: Session, limit: int = 20) -> list[DiscoveryRun]:
        models = (
            db.execute(
                select(DiscoveryRunModel).order_by(DiscoveryRunModel.started_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
