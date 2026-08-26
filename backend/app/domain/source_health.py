"""Domain model for per-source health tracking.

One row per distinct fetchable source: `"adzuna"` for the global job-board
search, `"lever:<slug>"` / `"greenhouse:<slug>"` for each watchlisted
company feed. Shared by Adzuna and every CompanyWatchlist entry so there is
exactly one place health state lives - see
app/repositories/source_health_repository.py.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import SourceHealthStatus

CONSECUTIVE_FAILURES_FOR_ERROR = 3
CONSECUTIVE_FAILURES_FOR_DEGRADED = 1


class SourceHealth(BaseModel):
    source_key: str
    status: SourceHealthStatus = SourceHealthStatus.UNKNOWN
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0
    last_error_category: str | None = None
    jobs_retrieved_last_run: int = 0
    avg_latency_ms: float | None = None
    attempts_count: int = 0
