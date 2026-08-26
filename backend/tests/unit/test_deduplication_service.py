"""Unit tests for exact/deterministic deduplication (stages 1-2) - no LLM,
real Postgres. Fuzzy (stage 3) matching is covered in
test_fuzzy_deduplication.py."""

from __future__ import annotations

from app.domain.enums import DuplicateMatchStage, JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.services import deduplication_service


def _posting(**overrides) -> RawJobPosting:
    defaults = {
        "title": "Graduate Data Scientist",
        "company": "Acme Corp",
        "location": "Melbourne, VIC",
        "source_type": JobSourceType.ADZUNA,
        "raw_description": "A great job description about data science.",
        "source_url": "https://example.com/jobs/123",
        "external_id": "123",
    }
    defaults.update(overrides)
    return RawJobPosting(**defaults)


def _store(db, posting: RawJobPosting):
    repo = DiscoveredJobRepository()
    fp = deduplication_service.compute_fingerprint(posting)
    desc_fp = deduplication_service.description_fingerprint(posting.raw_description)
    model = repo.create(
        db,
        posting=posting,
        fingerprint=fp,
        description_fingerprint=desc_fp,
        search_profile_id=None,
        discovery_run_id=None,
    )
    db.commit()
    return model


def test_same_source_and_external_id_is_a_duplicate(db):
    original = _posting()
    _store(db, original)

    repost = _posting(source_url="https://example.com/jobs/123?utm_source=other")
    match = deduplication_service.find_exact_or_fingerprint_duplicate(db, repost)

    assert match is not None
    assert match.stage == DuplicateMatchStage.EXACT_ID


def test_same_canonical_url_is_a_duplicate_even_with_different_external_id(db):
    original = _posting()
    _store(db, original)

    repost = _posting(
        external_id="999", source_url="https://example.com/jobs/123/?utm_source=linkedin"
    )
    match = deduplication_service.find_exact_or_fingerprint_duplicate(db, repost)

    assert match is not None
    assert match.stage == DuplicateMatchStage.CANONICAL_URL


def test_same_company_title_location_is_a_duplicate_with_no_url_or_id(db):
    original = _posting(source_url=None, external_id=None)
    _store(db, original)

    repost = _posting(
        source_url=None,
        external_id=None,
        title="  Graduate  Data Scientist ",  # different whitespace, same normalised text
        raw_description="A totally different description text.",
    )
    match = deduplication_service.find_exact_or_fingerprint_duplicate(db, repost)

    assert match is not None
    assert match.stage == DuplicateMatchStage.DETERMINISTIC_FINGERPRINT


def test_reposted_under_different_title_still_caught_by_description_fingerprint(db):
    original = _posting(source_url=None, external_id=None)
    _store(db, original)

    repost = _posting(
        source_url=None,
        external_id=None,
        title="Junior Data Scientist",  # different title
        company="Different Co",  # different company
        location="Sydney, NSW",  # different location
        raw_description=original.raw_description,  # but identical description
    )
    match = deduplication_service.find_exact_or_fingerprint_duplicate(db, repost)

    assert match is not None
    assert match.stage == DuplicateMatchStage.DETERMINISTIC_FINGERPRINT


def test_genuinely_different_posting_is_not_a_duplicate(db):
    original = _posting()
    _store(db, original)

    different = _posting(
        external_id="456",
        source_url="https://example.com/jobs/456",
        title="Senior Backend Engineer",
        company="Different Corp",
        location="Perth, WA",
        raw_description="A completely unrelated backend engineering role.",
    )
    match = deduplication_service.find_exact_or_fingerprint_duplicate(db, different)

    assert match is None


def test_canonical_url_ignores_trailing_slash_and_query_string():
    assert deduplication_service.canonical_url(
        "https://Example.com/jobs/123/?utm=1"
    ) == deduplication_service.canonical_url("https://example.com/jobs/123")
