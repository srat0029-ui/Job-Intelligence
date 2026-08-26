"""Research retrieval adapters.

`ResearchProvider` is the interface company/role research goes through -
`CompanyResearchService` never talks to httpx or any vendor SDK directly, so
adding a real search-API provider later (Brave/Serper/Google) is one new
class, not a change to the research pipeline. Two implementations exist
today:

- `HttpResearchProvider` - fetches one manually-supplied URL live over HTTP
  and returns its plain-text content. This is deliberately the "most
  practical mechanism available in the current environment": no web-search
  API credential is configured (see backend/.env), but a direct URL fetch
  needs no credential at all and reuses the same httpx + HTML-stripping
  approach already proven for Lever/Greenhouse. It is honest about what it
  is - a single-page fetch, not a search engine - and makes no network call
  a caller didn't explicitly ask for by supplying a URL.
- `FixtureResearchProvider` - deterministic, in-memory, keyed by URL. Used
  by tests and available as a local-dev fallback so research can be
  exercised without any network access.

A future `SearchApiResearchProvider` (a real search API) and a
`ManualPasteResearchProvider` (user pastes text directly, no fetch at all)
are both additive - same interface, no changes to CompanyResearchService.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.core.logging import get_logger
from app.ingestion.html_text import extract_published_at, extract_title, strip_html_for_research

logger = get_logger(__name__)

MAX_FETCH_TEXT_CHARS = 20_000


class RawResearchDocument(BaseModel):
    url: str
    domain: str
    title: str | None = None
    text: str
    published_at: datetime | None = None
    fetched_at: datetime


def domain_of(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.removeprefix("www.")


class ResearchProvider(ABC):
    """A source that can turn one URL into fetched, readable text."""

    @abstractmethod
    def fetch(self, url: str) -> RawResearchDocument:
        """Fetch and return one document's readable text.

        Implementations MUST raise (never silently return empty content) on
        failure, with the same error-shape convention as `JobSource`:
        `LookupError` for a not-found page, `TimeoutError` for a rate-limit/
        timeout, `ConnectionError` for another HTTP-level failure, and
        `ValueError` for unreadable content. Callers (CompanyResearchService)
        catch these and record a failed `ResearchSource` rather than letting
        one bad URL abort a whole research request.
        """
        raise NotImplementedError


class HttpResearchProvider(ResearchProvider):
    def __init__(self, *, client: httpx.Client | None = None, timeout: float = 15.0) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self, url: str) -> RawResearchDocument:
        try:
            response = self._client.get(
                url, headers={"User-Agent": "job-intelligence-research/1.0"}
            )
        except httpx.HTTPError as exc:
            logger.warning("research_fetch_failed", url=url, error=str(exc))
            raise ConnectionError(f"Could not fetch {url}: {exc}") from exc

        if response.status_code == 404:
            raise LookupError(f"Not found: {url}")
        if response.status_code == 429:
            raise TimeoutError(f"Rate-limited fetching: {url}")
        if response.status_code >= 400:
            raise ConnectionError(f"HTTP {response.status_code} fetching: {url}")

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise ValueError(f"Unsupported content-type {content_type!r} for: {url}")

        html = response.text
        text = strip_html_for_research(html)[:MAX_FETCH_TEXT_CHARS]
        if not text:
            raise ValueError(f"No readable text extracted from: {url}")

        return RawResearchDocument(
            url=url,
            domain=domain_of(url),
            title=extract_title(html),
            text=text,
            published_at=extract_published_at(html),
            fetched_at=datetime.now(UTC),
        )


class FixtureResearchProvider(ResearchProvider):
    """Deterministic, no-network provider keyed by exact URL - for tests and
    as a local-dev fallback with no network access."""

    def __init__(self, documents: dict[str, RawResearchDocument] | None = None) -> None:
        self._documents = documents or {}

    def register(self, url: str, document: RawResearchDocument) -> None:
        self._documents[url] = document

    def fetch(self, url: str) -> RawResearchDocument:
        document = self._documents.get(url)
        if document is None:
            raise LookupError(f"No fixture registered for: {url}")
        return document
