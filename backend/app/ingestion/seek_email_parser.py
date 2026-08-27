"""Parses a SEEK job-alert email (HTML body) into individual RawJobPostings.

Uses BeautifulSoup (the brief explicitly asks for "robust HTML parsing
rather than regex-only" here) rather than the regex-based `html_text.py`
used for ATS description HTML - alert emails contain multiple, separately
structured job listings that need to be found and split apart, not just
stripped to plain text.

Calibrated against real SEEK alert emails pulled from the connected inbox
(SEEK Recommendations digests, application-status notifications, and
reminder emails all share the same job-card component). Two things the
synthetic fixture this was originally built against got wrong:

1. Every link in a real SEEK alert - the job title, the thumbnail image,
   "View job", thumbs-up/down feedback, unsubscribe, footer nav - is
   wrapped in an opaque `email.s.seek.com.au` ESP click-tracking redirect,
   never a direct `seek.com.au/job/<id>` URL. There is nothing in the
   tracking URL's text to decode locally, so the real job id/URL can only
   be learned by following the redirect - see seek_link_resolver.py.
2. A real job card is not "a title anchor plus sibling company/location
   divs" - the *entire* card (title, company, badges, location, salary,
   highlight bullets) is wrapped in one `<a>`. That anchor's own
   `stripped_strings` is the complete, correctly-scoped field list for that
   one job with no risk of bleeding into a neighbouring card, which is what
   makes ">= 2 lines of the anchor's own text" a reliable "is this actually
   a job card, not a nav/feedback/unsubscribe link" signal - see
   `_is_job_card_anchor`.

Direct `seek.com(.au)/job/<id>` links are still supported (skips the
network round-trip entirely when the id is already in the URL) - this
covers both the original synthetic-fixture shape and any plain-text/direct
link SEEK might send elsewhere, so the parser degrades gracefully rather
than going to zero if a template changes again.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.domain.enums import JobSourceType
from app.ingestion.email_alert_parsing import clean_lines, job_container
from app.ingestion.job_source import RawJobPosting
from app.ingestion.seek_link_resolver import canonical_seek_job_url, extract_job_id
from app.services.location_service import AU_CITIES, AU_STATE_ABBREVIATIONS, FOREIGN_CITIES

_DIRECT_JOB_URL_RE = re.compile(r"seek\.com(?:\.au)?/job/(\d+)", re.IGNORECASE)

# Text that identifies a link as UI chrome rather than a job card, checked
# against an anchor's own first line - defense in depth alongside the
# ">= 2 own lines" structural gate (see module docstring).
_NAV_TEXT = {
    "view job",
    "view this job",
    "view more jobs",
    "apply now",
    "quick apply",
    "save job",
    "save this job",
    "see more",
    "how recommendations work",
    "rate your recent employer",
    "applied jobs",
    "protecting yourself online",
    "edit frequency",
    "unsubscribe",
    "privacy",
    "contact us",
    "yes",
    "no",
    "here",
}

# Badge/status text that appears *inside* a real job card's own lines but
# is never itself a field value (title/company/location/salary/snippet).
_BADGE_TEXT = {
    "strong applicant",
    "recently posted",
    "profile salary match",
}

# Trailing unit allows up to two words ("per year", "per annum", "incl
# super") - real SEEK salary lines commonly use a two-word suffix, not just
# "pa"/"pd".
_SALARY_RE = re.compile(
    r"\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$?[\d,]+(?:\.\d+)?)?(?:\s*/?\s*\w+(?:\s+\w+)?)?"
)

_LOCATION_MARKER_RE = re.compile(r"\((?:hybrid|remote|onsite)\)|\bremote\b", re.IGNORECASE)
_AU_STATE_WORD_RE = re.compile(
    r"\b(?:" + "|".join(AU_STATE_ABBREVIATIONS.values()) + r")\b"
)
_KNOWN_CITY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(c) for c in {**AU_CITIES, **FOREIGN_CITIES}) + r")\b",
    re.IGNORECASE,
)


def _looks_like_location(line: str) -> bool:
    return bool(
        _LOCATION_MARKER_RE.search(line)
        or _AU_STATE_WORD_RE.search(line)
        or _KNOWN_CITY_RE.search(line)
    )


def _href_is_seek_domain(href: str) -> bool:
    host = (urlparse(href).netloc or "").lower()
    return host.endswith("seek.com.au") or host.endswith("seek.com")


def _is_job_card_anchor(lines: list[str]) -> bool:
    """The structural gate that tells a real job card apart from nav/CTA/
    feedback/unsubscribe links without ever having to resolve them: every
    sampled non-job link in a real SEEK alert (button text, footer nav, an
    empty-text image link) carries at most one line of its own text, while
    every job card carries at least title + company."""
    if len(lines) < 2:
        return False
    return lines[0].lower() not in _NAV_TEXT


def _fields_from_lines(lines: list[str]) -> tuple[str, str, str | None, str | None, str] | None:
    content = [line for line in lines if line.lower() not in _BADGE_TEXT]
    if not content:
        return None
    title = content[0]
    company = content[1] if len(content) > 1 else "Unknown"
    rest = content[2:]

    location = next((line for line in rest if _looks_like_location(line)), None)
    salary_match = next((m for line in rest if (m := _SALARY_RE.search(line))), None)
    salary_text = salary_match.group(0) if salary_match else None

    snippet_lines = [
        line
        for line in rest
        if line != location and not (salary_match and salary_match.group(0) in line)
    ]
    return title, company, location, salary_text, " ".join(snippet_lines)


def _posting_from_fields(
    fields: tuple[str, str, str | None, str | None, str],
    *,
    source_url: str,
    external_id: str | None,
    message_id: str,
    received_at: datetime | None,
    extra_metadata: dict,
) -> RawJobPosting:
    title, company, location, salary_text, snippet = fields
    metadata: dict = {"gmail_message_id": message_id, **extra_metadata}
    if salary_text:
        metadata["salary_text"] = salary_text
    return RawJobPosting(
        title=title,
        company=company,
        location=location,
        source_url=source_url,
        source_type=JobSourceType.SEEK,
        raw_description=snippet or title,
        external_id=external_id,
        published_at=received_at,
        retrieved_at=received_at,
        source_metadata=metadata,
    )


def _direct_link_lines(anchor: Tag) -> list[str] | None:
    """Field lines for a *direct* `seek.com(.au)/job/<id>` link, where the
    anchor may only wrap the title with company/location as sibling
    elements (the original synthetic-fixture shape) - falls back to the
    surrounding container the same way the original parser did."""
    anchor_text = anchor.get_text(strip=True)
    container_lines = clean_lines(job_container(anchor))
    if anchor_text and anchor_text.lower() not in _NAV_TEXT:
        rest = [line for line in container_lines if line != anchor_text]
        return [anchor_text, *rest]
    return container_lines or None


def parse_seek_alert_email(
    html: str,
    *,
    message_id: str,
    received_at: datetime | None = None,
    resolve_link: Callable[[str], str | None] | None = None,
) -> list[RawJobPosting]:
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    postings: list[RawJobPosting] = []
    seen_job_ids: set[str] = set()
    seen_hrefs: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if href in seen_hrefs:
            continue

        direct_match = _DIRECT_JOB_URL_RE.search(href)
        if direct_match:
            job_id = direct_match.group(1)
            lines = _direct_link_lines(anchor)
            if lines is None:
                continue
            fields = _fields_from_lines(lines)
            if fields is None:
                continue
            seen_hrefs.add(href)
            if job_id in seen_job_ids:
                continue
            seen_job_ids.add(job_id)
            postings.append(
                _posting_from_fields(
                    fields,
                    source_url=canonical_seek_job_url(job_id),
                    external_id=job_id,
                    message_id=message_id,
                    received_at=received_at,
                    extra_metadata={},
                )
            )
            continue

        if not _href_is_seek_domain(href):
            continue

        own_lines = clean_lines(anchor)
        if not _is_job_card_anchor(own_lines):
            continue
        fields = _fields_from_lines(own_lines)
        if fields is None:
            continue

        seen_hrefs.add(href)

        if resolve_link is None:
            # No resolver configured - can't recover the destination job id
            # from an opaque tracking link (see module docstring), so this
            # candidate can't be turned into a posting at all.
            continue

        resolved_url = resolve_link(href)
        if resolved_url is None:
            # Resolution failed (timeout/network error) - degrade
            # gracefully rather than dropping a job the parser was
            # otherwise confident about: keep the tracking URL as the
            # source and skip dedup-by-id for this one posting.
            postings.append(
                _posting_from_fields(
                    fields,
                    source_url=href,
                    external_id=None,
                    message_id=message_id,
                    received_at=received_at,
                    extra_metadata={"seek_tracking_url": href, "seek_resolution_failed": True},
                )
            )
            continue

        job_id = extract_job_id(resolved_url)
        if job_id is None:
            # Resolved to something that isn't a job page (logo -> seek
            # homepage, thumbs-up/down -> a survey, unsubscribe, etc) - not
            # a job link after all.
            continue
        if job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)
        postings.append(
            _posting_from_fields(
                fields,
                source_url=canonical_seek_job_url(job_id),
                external_id=job_id,
                message_id=message_id,
                received_at=received_at,
                extra_metadata={"seek_tracking_url": href},
            )
        )

    return postings
