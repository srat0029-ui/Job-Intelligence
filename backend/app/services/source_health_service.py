"""Wraps a single JobSource.fetch() call with timing + health bookkeeping.

Every source fetch in DiscoveryService goes through
`fetch_with_health_tracking`, whether it's Adzuna (which never raises - see
adzuna_source.py) or a Lever/Greenhouse company feed (which raises typed
exceptions on failure - see lever_source.py/greenhouse_source.py). This is
also where "failure isolation per source" (PART 18) actually lives: an
exception here is caught, categorised, and recorded, and the caller always
gets back a plain list (possibly empty) rather than a propagated exception.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.source_health import SourceHealth
from app.ingestion.job_source import JobSource, RawJobPosting
from app.repositories.source_health_repository import SourceHealthRepository

logger = get_logger(__name__)


def _categorize_error(exc: Exception) -> str:
    return type(exc).__name__


def fetch_with_health_tracking(
    db: Session,
    *,
    source_key: str,
    source: JobSource,
    repository: SourceHealthRepository | None = None,
) -> tuple[list[RawJobPosting], SourceHealth]:
    repository = repository or SourceHealthRepository()
    start = time.perf_counter()
    try:
        postings = source.fetch()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this IS the isolation boundary
        category = _categorize_error(exc)
        logger.warning("source_fetch_failed", source_key=source_key, error_category=category)
        health = repository.record_failure(db, source_key, error_category=category)
        return [], health

    latency_ms = (time.perf_counter() - start) * 1000
    health = repository.record_success(
        db, source_key, jobs_retrieved=len(postings), latency_ms=latency_ms
    )
    return postings, health
