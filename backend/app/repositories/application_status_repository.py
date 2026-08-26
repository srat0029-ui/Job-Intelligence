"""Data access for the application-status history."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.application_status import ApplicationStatusEventModel
from app.domain.application_status import ApplicationStatusEvent
from app.domain.enums import ApplicationStatus


def _to_domain(model: ApplicationStatusEventModel) -> ApplicationStatusEvent:
    return ApplicationStatusEvent(
        id=model.id,
        job_id=model.job_id,
        status=ApplicationStatus(model.status),
        note=model.note,
        created_at=model.created_at,
    )


class ApplicationStatusRepository:
    def add_event(
        self, db: Session, *, job_id: UUID, status: ApplicationStatus, note: str | None = None
    ) -> ApplicationStatusEvent:
        model = ApplicationStatusEventModel(job_id=job_id, status=status.value, note=note)
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def list_for_job(self, db: Session, job_id: UUID) -> list[ApplicationStatusEvent]:
        models = (
            db.execute(
                select(ApplicationStatusEventModel)
                .where(ApplicationStatusEventModel.job_id == job_id)
                .order_by(ApplicationStatusEventModel.created_at.asc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
