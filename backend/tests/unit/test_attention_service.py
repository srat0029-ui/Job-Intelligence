"""Unit tests for the internal attention/notification system."""

from __future__ import annotations

import uuid

from app.domain.enums import AttentionItemStatus, AttentionItemType, JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.services import deduplication_service
from app.services.attention_service import AttentionService


def _real_discovered_job_id(db) -> uuid.UUID:
    """Attention items FK to a real discovered_jobs row (CASCADE delete),
    so tests need an actual row rather than a random UUID."""
    posting = RawJobPosting(
        title="Graduate AI Engineer",
        company="Acme",
        source_type=JobSourceType.ADZUNA,
        raw_description="desc",
        external_id=str(uuid.uuid4()),
    )
    repo = DiscoveredJobRepository()
    model = repo.create(
        db,
        posting=posting,
        fingerprint=deduplication_service.compute_fingerprint(posting),
        description_fingerprint=deduplication_service.description_fingerprint(posting.raw_description),
        search_profile_id=None,
        discovery_run_id=None,
    )
    db.commit()
    return model.id


def test_notify_high_priority_job_creates_unread_item(db):
    service = AttentionService()
    job_id = _real_discovered_job_id(db)

    item = service.notify_high_priority_job(
        db,
        discovered_job_id=job_id,
        job_title="Graduate AI Engineer",
        company="Acme",
        priority="apply_asap",
    )

    assert item.item_type == AttentionItemType.HIGH_PRIORITY_JOB
    assert item.status == AttentionItemStatus.UNREAD
    assert item.related_discovered_job_id == job_id
    assert "Graduate AI Engineer" in item.title


def test_count_unread_and_mark_read(db):
    service = AttentionService()
    service.notify_source_unhealthy(db, source_key="lever:acme", consecutive_failures=3)
    item2 = service.notify_analysis_failures(db, failed_count=2, discovery_run_id=uuid.uuid4())

    assert service.count_unread(db) == 2

    service.mark_read(db, item2.id)
    assert service.count_unread(db) == 1

    recent_unread = service.list_recent(db, unread_only=True)
    assert len(recent_unread) == 1
    assert recent_unread[0].item_type == AttentionItemType.SOURCE_UNHEALTHY


def test_mark_read_on_missing_item_returns_none(db):
    service = AttentionService()
    assert service.mark_read(db, uuid.uuid4()) is None
