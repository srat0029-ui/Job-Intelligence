"""Unit tests for SQL-side filtering/sorting/pagination of the opportunity
feed (DiscoveredJobRepository.list_paginated / OpportunityService)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.domain.enums import DiscoveredJobStatus, GeographicEligibility, JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.main import app
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.services import deduplication_service
from app.services.opportunity_service import OpportunityService


def _make_discovered_job(
    db, *, title: str, score: float | None, status=DiscoveredJobStatus.ANALYSED
):
    posting = RawJobPosting(
        title=title,
        company="Acme",
        location="Melbourne, VIC",
        source_type=JobSourceType.ADZUNA,
        raw_description=f"{title} description",
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
        country="AU",
        geographic_eligibility=GeographicEligibility.ELIGIBLE,
        geographic_eligibility_reason="Located in Melbourne, VIC, Australia.",
    )
    model.status = status.value
    model.latest_overall_score = score
    model.latest_recommendation = "apply" if score else None
    db.commit()
    return model


def test_pagination_returns_correct_page_and_total(db):
    for i in range(5):
        _make_discovered_job(db, title=f"Job {i}", score=float(i * 10))

    service = OpportunityService()
    page1 = service.list_opportunities(db, page=1, page_size=2, sort_by="score", descending=True)

    assert page1.total == 5
    assert len(page1.items) == 2
    assert page1.items[0].overall_score == 40.0  # highest score first
    assert page1.items[1].overall_score == 30.0

    page2 = service.list_opportunities(db, page=2, page_size=2, sort_by="score", descending=True)
    assert page2.items[0].overall_score == 20.0


def test_min_score_filter_applies_in_sql(db):
    _make_discovered_job(db, title="Low", score=20.0)
    _make_discovered_job(db, title="High", score=90.0)

    service = OpportunityService()
    page = service.list_opportunities(db, min_score=50.0)

    assert page.total == 1
    assert page.items[0].title == "High"


def test_rejected_jobs_hidden_by_default_and_shown_when_requested(db):
    _make_discovered_job(
        db, title="Rejected", score=None, status=DiscoveredJobStatus.PREFILTER_REJECTED
    )
    _make_discovered_job(db, title="Eligible", score=80.0)

    service = OpportunityService()
    default_page = service.list_opportunities(db)
    assert default_page.total == 1
    assert default_page.items[0].title == "Eligible"

    full_page = service.list_opportunities(db, include_rejected=True)
    assert full_page.total == 2


def test_reviewed_filter(db):
    unreviewed = _make_discovered_job(db, title="Unreviewed", score=50.0)
    _make_discovered_job(db, title="Reviewed", score=60.0)

    service = OpportunityService()
    reviewed_job = service.mark_reviewed(db, unreviewed.id)
    assert reviewed_job is not None
    # Re-fetch the OTHER job and mark it reviewed too, so we have one of each.
    other = next(d for d in DiscoveredJobRepository().list_all(db) if d.title == "Reviewed")

    unreviewed_page = service.list_opportunities(db, reviewed=False)
    assert unreviewed_page.total == 1
    assert unreviewed_page.items[0].title == "Reviewed"

    reviewed_page = service.list_opportunities(db, reviewed=True)
    assert reviewed_page.total == 1
    assert reviewed_page.items[0].title == "Unreviewed"
    assert other.reviewed_at is None  # sanity check we didn't touch the other row


def test_ignore_sets_archived_status(db):
    job = _make_discovered_job(
        db, title="To Ignore", score=None, status=DiscoveredJobStatus.AWAITING_ANALYSIS
    )
    service = OpportunityService()

    ignored = service.ignore(db, job.id)
    assert ignored is not None
    assert ignored.status == DiscoveredJobStatus.ARCHIVED


def test_page_size_is_capped_at_the_api_boundary(db):
    """The service itself takes any page_size (it's a building block); the
    HTTP API is where an out-of-range value must be rejected, per Part 16's
    server-side pagination requirement."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/api/discovery/opportunities", params={"page_size": 10_000})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
