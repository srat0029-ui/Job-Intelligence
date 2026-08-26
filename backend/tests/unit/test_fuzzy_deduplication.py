"""Unit tests for stage-3 fuzzy deduplication - the safety-critical part.

Two properties matter most here:
1. The same job reworded between an aggregator and a direct posting IS
   recognised as a duplicate (a false negative here means a duplicate
   opportunity gets analysed twice - wasteful, not dangerous).
2. Two genuinely DIFFERENT roles at the same company are NEVER merged,
   even when their titles/descriptions share vocabulary - a false
   positive here would silently discard a real, distinct opportunity,
   which the brief explicitly calls out as the dangerous failure mode.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.enums import JobSourceType
from app.ingestion.job_source import RawJobPosting
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.services import deduplication_service


def _posting(**overrides) -> RawJobPosting:
    defaults: dict = {
        "title": "Graduate Data Scientist",
        "company": "Data Co",
        "location": "Melbourne",
        "source_type": JobSourceType.LEVER,
        "raw_description": "Join our data science team building ML models with Python.",
        "external_id": None,
        "source_url": None,
        "published_at": datetime(2026, 1, 15, tzinfo=UTC),
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


def test_reworded_title_same_company_same_description_is_a_fuzzy_duplicate(db):
    """The example from the brief: "Graduate Data Scientist" (Adzuna) vs
    "2027 Graduate Program - Data Science" (direct posting) at the same
    company, with substantially the same description text."""
    original = _posting(
        title="Graduate Data Scientist",
        raw_description=(
            "Join our data science team. You will build machine learning models using Python, "
            "work with large datasets, and collaborate with senior data scientists on real "
            "business problems. We're looking for graduates with strong analytical skills."
        ),
        source_type=JobSourceType.ADZUNA,
        external_id="adzuna-1",
    )
    _store(db, original)

    reworded = _posting(
        title="2027 Graduate Program - Data Science",
        # Semantically the same posting, reworded/reordered slightly - not a
        # byte-for-byte match, so this must NOT be caught by the stage-2
        # exact description-fingerprint check; it should only be caught by
        # stage-3 fuzzy similarity.
        raw_description=(
            "You'll join our data science team building machine learning models with Python, "
            "working with large datasets alongside senior data scientists on real business "
            "problems. We are looking for graduates with strong analytical skills."
        ),
        source_type=JobSourceType.LEVER,
        external_id="lever-1",
        source_url="https://jobs.lever.co/data-co/1",
    )

    # Must not match at the exact/deterministic stages first (different id,
    # different URL, different title -> different company/title/location
    # fingerprint, different exact description).
    assert deduplication_service.find_exact_or_fingerprint_duplicate(db, reworded) is None

    match = deduplication_service.find_fuzzy_duplicate(db, reworded)
    assert match is not None
    assert match.confidence >= deduplication_service.AUTO_MERGE_THRESHOLD
    assert "same company" in match.reason


def test_two_different_roles_at_same_company_are_never_merged(db):
    """The dangerous false-positive case the brief explicitly warns about:
    two DIFFERENT graduate roles at the same company must stay separate."""
    data_scientist = _posting(
        title="Graduate Data Scientist",
        raw_description=(
            "Join our data science team. Build machine learning models using Python and "
            "statistical analysis. Strong maths background required."
        ),
    )
    _store(db, data_scientist)

    software_engineer = _posting(
        title="Graduate Software Engineer",
        raw_description=(
            "Join our engineering team. Build backend services using Java and SQL. "
            "Strong computer science fundamentals required."
        ),
        external_id="lever-2",
    )

    match = deduplication_service.find_fuzzy_duplicate(db, software_engineer)
    assert match is None


def test_same_title_different_company_is_never_merged(db):
    """The company-match gate must never be bypassed by title/description
    similarity alone."""
    original = _posting(company="Data Co")
    _store(db, original)

    same_title_other_company = _posting(company="Totally Different Corp", external_id="x-1")

    match = deduplication_service.find_fuzzy_duplicate(db, same_title_other_company)
    assert match is None


def test_low_title_similarity_rejected_even_with_high_description_overlap(db):
    """Boilerplate company descriptions ("About us...") can coincidentally
    overlap a lot between unrelated postings - title similarity below the
    floor must reject the match regardless of description similarity."""
    boilerplate = (
        "About Data Co: we are a leading technology company committed to innovation, "
        "diversity, and excellence. We offer competitive benefits and a collaborative culture."
    )
    original = _posting(title="Graduate Data Scientist", raw_description=boilerplate)
    _store(db, original)

    unrelated = _posting(
        title="Senior Finance Manager",
        raw_description=boilerplate,
        external_id="x-2",
    )

    match = deduplication_service.find_fuzzy_duplicate(db, unrelated)
    assert match is None


def test_uncertain_similarity_is_a_false_negative_not_a_merge(db):
    """Per the brief: prefer false negatives over risky false positives. Two
    different early-career roles at the same company, sharing only generic
    "graduate role" vocabulary, must not merge."""
    original = _posting(
        title="Graduate Data Analyst",
        raw_description="Analyse sales data and build dashboards using SQL and Power BI.",
    )
    _store(db, original)

    different_role = _posting(
        title="Graduate Marketing Coordinator",
        raw_description="Coordinate marketing campaigns and manage social media channels.",
        external_id="x-3",
    )

    match = deduplication_service.find_fuzzy_duplicate(db, different_role)
    assert match is None


def test_fuzzy_search_is_bounded_by_company_and_date_window(db):
    """The candidate set must be bounded (never an unbounded table scan) -
    a same-titled job at the same company well outside the date window,
    and one for a different company, must not be pulled in as noise."""
    _store(db, _posting(published_at=datetime(2020, 1, 1, tzinfo=UTC), external_id="old-1"))
    _store(
        db,
        _posting(
            company="Other Co",
            published_at=datetime(2026, 1, 15, tzinfo=UTC),
            external_id="other-1",
        ),
    )

    candidate = _posting(
        title="Graduate Data Scientist",
        published_at=datetime(2026, 1, 16, tzinfo=UTC),
        external_id="new-1",
    )
    match = deduplication_service.find_fuzzy_duplicate(db, candidate)
    # The only real candidate (old-1) is outside the date window, and
    # other-1 is a different company - so nothing should match.
    assert match is None
