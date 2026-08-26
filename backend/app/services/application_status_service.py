"""Business logic for the (manual, no auto-apply) application status
tracker. Every transition is recorded as an event so outcome data
(interview? offer?) can eventually calibrate the scoring weights - see
README "how application outcome data will eventually calibrate scoring"."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.application_status import ApplicationStatusEvent
from app.domain.enums import ApplicationStatus
from app.domain.job import Job
from app.repositories.application_status_repository import ApplicationStatusRepository
from app.repositories.job_repository import JobRepository


class ApplicationStatusService:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        event_repository: ApplicationStatusRepository | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._event_repository = event_repository or ApplicationStatusRepository()

    def set_status(
        self, db: Session, job_id: UUID, status: ApplicationStatus, note: str | None = None
    ) -> Job | None:
        job = self._job_repository.set_application_status(db, job_id, status)
        if job is None:
            return None
        self._event_repository.add_event(db, job_id=job_id, status=status, note=note)
        return job

    def history(self, db: Session, job_id: UUID) -> list[ApplicationStatusEvent]:
        return self._event_repository.list_for_job(db, job_id)
