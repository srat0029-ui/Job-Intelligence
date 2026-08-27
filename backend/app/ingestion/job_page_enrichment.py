"""Optional, best-effort enrichment of an email-alert posting using its
original job-listing URL (Part 6 of the milestone brief).

Never mandatory and never retried: a single attempt, and on any failure
(non-200, timeout, connection error, or content that looks like a login
wall) the posting is kept exactly as parsed from the alert email, just
flagged `source_metadata["description_partial"] = True` so the UI can
still show it and link to the original listing. No browser automation, no
bypassing anti-bot/login protections, no repeated hits on a failing URL.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.ingestion.html_text import strip_html_for_research
from app.ingestion.job_source import RawJobPosting

logger = get_logger(__name__)

ENRICHMENT_TIMEOUT_SECONDS = 8.0
MIN_ENRICHED_TEXT_LENGTH = 200
_LOGIN_WALL_HINTS = [
    "sign in to continue",
    "join now to see",
    "log in to view",
    "please sign in",
    "log in to apply",
    # LinkedIn's own unauthenticated redirect page for a jobs/view/<id> URL
    # ("Sign in / We're signing you in / Discover people, jobs, and more")
    # was slipping through this list entirely - every unauthenticated
    # LinkedIn job link resolves here, so this one phrase alone was
    # silently overwriting a real (if short) alert-email description with
    # generic LinkedIn chrome for every single LinkedIn posting enriched.
    "we're signing you in",
    "discover people, jobs, and more",
]
# A real job description doesn't rattle off LinkedIn's own footer nav - if
# several of these appear together, the fetched page is LinkedIn chrome
# (a login wall, home page, or footer), not the posting, regardless of
# whether one of the phrases above happened to match.
_SITE_CHROME_HINTS = [
    "accessibility",
    "user agreement",
    "cookie policy",
    "copyright policy",
    "brand policy",
    "guest controls",
    "community guidelines",
]
MIN_SITE_CHROME_HINTS_FOR_BLOCK = 3


def _mark_partial(posting: RawJobPosting) -> RawJobPosting:
    updated = posting.model_copy(deep=True)
    updated.source_metadata = {**updated.source_metadata, "description_partial": True}
    return updated


def enrich_posting(posting: RawJobPosting, *, client: httpx.Client | None = None) -> RawJobPosting:
    """Returns a copy of `posting` with a richer `raw_description` if the
    original URL loaded successfully and looks like real content; otherwise
    returns a copy marked `description_partial` with the alert-only content
    untouched."""
    if not posting.source_url:
        return posting

    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=ENRICHMENT_TIMEOUT_SECONDS, follow_redirects=True
    )
    try:
        response = http_client.get(posting.source_url)
    except httpx.HTTPError as exc:
        logger.info("job_page_enrichment_failed", url=posting.source_url, error=str(exc))
        return _mark_partial(posting)
    finally:
        if owns_client:
            http_client.close()

    if response.status_code != 200:
        logger.info(
            "job_page_enrichment_non_200", url=posting.source_url, status=response.status_code
        )
        return _mark_partial(posting)

    text = strip_html_for_research(response.text)
    lowered = text.lower()
    chrome_hint_count = sum(1 for hint in _SITE_CHROME_HINTS if hint in lowered)
    if (
        len(text) < MIN_ENRICHED_TEXT_LENGTH
        or any(hint in lowered for hint in _LOGIN_WALL_HINTS)
        or chrome_hint_count >= MIN_SITE_CHROME_HINTS_FOR_BLOCK
    ):
        logger.info("job_page_enrichment_blocked_or_thin", url=posting.source_url)
        return _mark_partial(posting)

    updated = posting.model_copy(deep=True)
    updated.raw_description = text
    return updated
