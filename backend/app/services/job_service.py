"""Business logic for creating and listing jobs, via the ingestion layer."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.job import Job
from app.ingestion.job_source import JobSource
from app.repositories.job_repository import JobRepository


class JobService:
    def __init__(self, repository: JobRepository | None = None) -> None:
        self._repository = repository or JobRepository()

    def add_job(self, db: Session, source: JobSource) -> list[Job]:
        """Pulls postings from any JobSource (today: only ManualJobSource,
        which yields exactly one posting) and persists each as a Job."""
        postings = source.fetch()
        return [self._repository.create_from_posting(db, posting) for posting in postings]

    def get_job(self, db: Session, job_id: UUID) -> Job | None:
        return self._repository.get(db, job_id)

    def list_jobs(self, db: Session) -> list[Job]:
        return self._repository.list_all(db)
