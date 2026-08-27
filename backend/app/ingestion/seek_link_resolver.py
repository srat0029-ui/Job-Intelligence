"""Resolves a SEEK email click-tracking URL (`email.s.seek.com.au/...`) to
the canonical SEEK job URL it points to.

Real SEEK alert emails (see seek_email_parser.py's docstring) wrap every
link in an opaque ESP tracking redirect - the job id is not recoverable from
the tracking URL's text alone, so the only way to learn the real destination
is to follow the redirect. This is a single bounded HTTP GET with redirects
followed (SEEK's tracking link is one 302 hop straight to
`au.seek.com/job/<id>?...`, observed directly against the real inbox) -
never scrapes the destination page's content, never retries more than once,
and never authenticates or bypasses anything. A failing/slow link is
isolated to that one link (returns None) rather than raising, so one bad
tracking URL can't take down a whole email's worth of postings.
"""

from __future__ import annotations

import re

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

RESOLVE_TIMEOUT_SECONDS = 6.0
MAX_REDIRECTS = 5
MAX_ATTEMPTS = 2  # one retry on a transient failure, no more

JOB_URL_RE = re.compile(r"seek\.com(?:\.au)?/job/(\d+)", re.IGNORECASE)


def canonical_seek_job_url(job_id: str) -> str:
    return f"https://www.seek.com.au/job/{job_id}"


def extract_job_id(url: str) -> str | None:
    match = JOB_URL_RE.search(url)
    return match.group(1) if match else None


class SeekLinkResolver:
    """Follows a tracking link to its final destination, once per unique
    URL. The cache is expected to live for exactly one Gmail sync (threaded
    in by the caller, or created fresh per instance) - see
    job_alert_email_source.py, which shares one resolver/cache across every
    SEEK message in a `fetch()` call so a link repeated within or across
    messages (e.g. a duplicate title + "View job" CTA) is only ever
    resolved once."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        cache: dict[str, str | None] | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=RESOLVE_TIMEOUT_SECONDS,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
        )
        self._cache: dict[str, str | None] = cache if cache is not None else {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def resolve(self, tracking_url: str) -> str | None:
        """Returns the final destination URL, or None if it could not be
        resolved (network error, timeout, or too many redirects) after a
        small bounded number of attempts. Never raises."""
        if tracking_url in self._cache:
            return self._cache[tracking_url]

        final_url: str | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._client.get(tracking_url)
                final_url = str(response.url)
                break
            except httpx.HTTPError as exc:
                logger.info(
                    "seek_link_resolve_failed",
                    url=tracking_url,
                    attempt=attempt,
                    error=str(exc),
                )
                continue

        self._cache[tracking_url] = final_url
        return final_url
