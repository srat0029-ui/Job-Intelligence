"""Job ingestion adapters.

`JobSource` is the interface every job source implements - whether the user
pastes a description by hand, an automated adapter (Adzuna) polls an API, or
a future adapter pulls listings from Seek/LinkedIn/a career page/an email
inbox. Nothing in JobService, ExtractionService, or the API routes needs to
change when a new adapter is added; they only ever depend on
`RawJobPosting` and the `JobSource` ABC.

`ManualJobSource` (user-pasted text) and `AdzunaJobSource` (see
adzuna_source.py) are the two implementations so far. Scraping third-party
job boards whose terms/technical restrictions make that inappropriate
(LinkedIn, Seek) is explicitly out of scope - see project instructions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import JobSourceType


class RawJobPosting(BaseModel):
    """The canonical, source-agnostic shape every JobSource normalises into.

    Only `title`/`company`/`raw_description`/`source_type` are required -
    the rest are optional "if known" fields so a manual paste (which only
    ever has the required ones) and a rich API response (Adzuna, which can
    supply salary/dates/external IDs) share one type without either source
    needing to fake data it doesn't have. Field names are deliberately
    generic (not `adzuna_id`, `adzuna_category`, ...) so no vendor-specific
    concept leaks into core domain code - vendor-specific detail belongs in
    `source_metadata` instead.
    """

    title: str
    company: str
    location: str | None = None
    source_url: str | None = None
    source_type: JobSourceType
    raw_description: str

    # Optional canonical fields - populated by richer sources, left as None
    # by ManualJobSource.
    external_id: str | None = None
    remote_type: str | None = None  # "remote" | "hybrid" | "onsite"
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    employment_type: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    source_metadata: dict = Field(default_factory=dict)


class JobSource(ABC):
    """A source that can produce zero or more RawJobPosting records."""

    source_type: JobSourceType

    @abstractmethod
    def fetch(self) -> list[RawJobPosting]:
        """Return newly available postings. Manual sources return what the
        user just submitted; automated sources (future) would poll/scrape
        and return any new listings since the last run."""
        raise NotImplementedError


class ManualJobSource(JobSource):
    """Wraps a single user-pasted job description as a RawJobPosting.

    This is the only JobSource implementation in V1. It exists as a class
    (rather than JobService building the dict inline) purely so the
    ingestion boundary is real from day one - adding SeekJobSource later is
    additive, not a refactor of JobService.
    """

    source_type = JobSourceType.MANUAL

    def __init__(
        self,
        *,
        title: str,
        company: str,
        raw_description: str,
        location: str | None = None,
        source_url: str | None = None,
    ) -> None:
        self._posting = RawJobPosting(
            title=title,
            company=company,
            location=location,
            source_url=source_url,
            source_type=self.source_type,
            raw_description=raw_description,
        )

    def fetch(self) -> list[RawJobPosting]:
        return [self._posting]
