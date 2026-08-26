"""Unit tests for manual application-status tracking (no auto-apply)."""

from __future__ import annotations

from app.domain.enums import ApplicationStatus, JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.repositories.job_repository import JobRepository
from app.services.application_status_service import ApplicationStatusService


def _make_job(db):
    posting = RawJobPosting(
        title="Graduate Data Scientist",
        company="Acme",
        source_type=JobSourceType.MANUAL,
        raw_description="desc",
    )
    return JobRepository().create_from_posting(db, posting)


def test_set_status_updates_job_and_records_history(db):
    job = _make_job(db)
    service = ApplicationStatusService()

    updated = service.set_status(db, job.id, ApplicationStatus.INTERESTED)
    assert updated is not None
    assert updated.application_status == ApplicationStatus.INTERESTED

    updated = service.set_status(db, job.id, ApplicationStatus.APPLIED, note="Applied via website")
    assert updated.application_status == ApplicationStatus.APPLIED

    history = service.history(db, job.id)
    assert [e.status for e in history] == [ApplicationStatus.INTERESTED, ApplicationStatus.APPLIED]
    assert history[1].note == "Applied via website"


def test_set_status_on_missing_job_returns_none(db):
    import uuid

    service = ApplicationStatusService()
    result = service.set_status(db, uuid.uuid4(), ApplicationStatus.INTERESTED)
    assert result is None
