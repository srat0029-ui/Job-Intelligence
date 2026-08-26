"""Job ingestion adapters.

`JobSource` is the interface every job source implements - whether the user
pastes a description by hand (V1) or a future adapter pulls listings from
Seek/LinkedIn/a career page/an email inbox. Nothing in JobService,
ExtractionService, or the API routes needs to change when a new adapter is
added; they only ever depend on `RawJobPosting` and the `JobSource` ABC.

V1 intentionally ships only `ManualJobSource`. Scraping third-party job
boards is fragile, likely violates their terms of service, and is out of
scope for this phase - see project instructions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.domain.enums import JobSourceType


class RawJobPosting(BaseModel):
    """The minimum a job source must supply before extraction can run."""

    title: str
    company: str
    location: str | None = None
    source_url: str | None = None
    source_type: JobSourceType
    raw_description: str


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
