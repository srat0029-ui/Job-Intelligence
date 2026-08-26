"""Domain model for the target-company watchlist.

Represents an employer the user wants monitored directly via its ATS
(Lever/Greenhouse today), independent of broad job-board search. Health
fields (`last_checked_at`, `last_successful_check_at`, `status`) are not
stored here - they're read from `SourceHealth` keyed by
`source_key` (see `source_key` property below) so there is one source of
truth for health bookkeeping shared with Adzuna, not a second copy that can
drift out of sync.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import ATSType, CompanyPriority


class CompanyWatchlistEntry(BaseModel):
    id: UUID | None = None
    company_name: str
    enabled: bool = True
    priority: CompanyPriority = CompanyPriority.NORMAL
    careers_url: str | None = None
    ats_type: ATSType
    ats_identifier: str  # Lever site slug / Greenhouse board token
    preferred_locations: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def source_key(self) -> str:
        """The SourceHealth key this entry's fetches are tracked under."""
        return f"{self.ats_type.value}:{self.ats_identifier}"
