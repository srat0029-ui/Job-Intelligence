"""Data access for job postings."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job import JobModel
from app.domain.enums import ApplicationStatus, JobSourceType
from app.domain.job import Job
from app.ingestion.job_source import RawJobPosting


def _to_domain(model: JobModel) -> Job:
    return Job(
        id=model.id,
        title=model.title,
        company=model.company,
        location=model.location,
        source_url=model.source_url,
        source_type=JobSourceType(model.source_type),
        raw_description=model.raw_description,
        application_status=(
            ApplicationStatus(model.application_status) if model.application_status else None
        ),
        created_at=model.created_at.isoformat() if model.created_at else None,
    )


class JobRepository:
    def create_from_posting(self, db: Session, posting: RawJobPosting) -> Job:
        model = JobModel(
            title=posting.title,
            company=posting.company,
            location=posting.location,
            source_url=posting.source_url,
            source_type=posting.source_type.value,
            raw_description=posting.raw_description,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def get(self, db: Session, job_id: UUID) -> Job | None:
        model = db.get(JobModel, job_id)
        return _to_domain(model) if model else None

    def list_all(self, db: Session) -> list[Job]:
        models = db.execute(select(JobModel).order_by(JobModel.created_at.desc())).scalars().all()
        return [_to_domain(m) for m in models]

    def get_many(self, db: Session, job_ids: list[UUID]) -> dict[UUID, Job]:
        if not job_ids:
            return {}
        models = db.execute(select(JobModel).where(JobModel.id.in_(job_ids))).scalars().all()
        return {m.id: _to_domain(m) for m in models}

    def set_application_status(
        self, db: Session, job_id: UUID, status: ApplicationStatus
    ) -> Job | None:
        model = db.get(JobModel, job_id)
        if model is None:
            return None
        model.application_status = status.value
        db.commit()
        db.refresh(model)
        return _to_domain(model)
