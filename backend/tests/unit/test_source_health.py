"""Unit tests for per-source health tracking and its failure-isolation
wrapper (fetch_with_health_tracking)."""

from __future__ import annotations

import pytest

from app.domain.enums import JobSourceType, SourceHealthStatus
from app.ingestion.job_source import JobSource, RawJobPosting
from app.repositories.source_health_repository import SourceHealthRepository
from app.services.source_health_service import fetch_with_health_tracking


class _SucceedingSource(JobSource):
    source_type = JobSourceType.MANUAL

    def fetch(self) -> list[RawJobPosting]:
        return [
            RawJobPosting(
                title="Job",
                company="Acme",
                source_type=self.source_type,
                raw_description="desc",
            )
        ]


class _FailingSource(JobSource):
    source_type = JobSourceType.MANUAL

    def fetch(self) -> list[RawJobPosting]:
        raise ConnectionError("simulated network failure")


def test_successful_fetch_records_healthy_status(db):
    postings, health = fetch_with_health_tracking(
        db, source_key="test-source", source=_SucceedingSource()
    )
    assert len(postings) == 1
    assert health.status == SourceHealthStatus.HEALTHY
    assert health.consecutive_failures == 0
    assert health.jobs_retrieved_last_run == 1


def test_failed_fetch_is_isolated_and_returns_empty_list(db):
    postings, health = fetch_with_health_tracking(
        db, source_key="test-source", source=_FailingSource()
    )
    assert postings == []  # never raises out to the caller
    assert health.consecutive_failures == 1
    assert health.last_error_category == "ConnectionError"


@pytest.mark.parametrize("attempt_count,expected_status", [(1, "degraded"), (3, "error")])
def test_status_escalates_with_consecutive_failures(db, attempt_count, expected_status):
    repo = SourceHealthRepository()
    health = None
    for _ in range(attempt_count):
        _, health = fetch_with_health_tracking(
            db, source_key="flaky-source", source=_FailingSource(), repository=repo
        )
    assert health.status.value == expected_status


def test_recovery_resets_consecutive_failures(db):
    repo = SourceHealthRepository()
    fetch_with_health_tracking(db, source_key="s", source=_FailingSource(), repository=repo)
    fetch_with_health_tracking(db, source_key="s", source=_FailingSource(), repository=repo)
    _, health = fetch_with_health_tracking(
        db, source_key="s", source=_SucceedingSource(), repository=repo
    )
    assert health.consecutive_failures == 0
    assert health.status == SourceHealthStatus.HEALTHY
