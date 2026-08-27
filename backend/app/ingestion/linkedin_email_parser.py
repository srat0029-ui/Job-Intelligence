"""Parses a LinkedIn job-alert email (HTML body) into individual
RawJobPostings. Same anchor-based, template-agnostic strategy as
seek_email_parser.py (shared via email_alert_parsing.py).

Calibrated against real LinkedIn alert emails pulled from the connected
inbox. A real job card is wrapped by (at least) three separate `<a
href="...linkedin.com/.../jobs/view/<id>...">` anchors sharing the exact
same job id - a company-logo image link (no text), the full card (title +
"Company · Location" + zero or more badge/status lines), and a bare title
link. Earlier versions of this parser processed whichever anchor came first
in document order and fell back to a container walk for the rest - when
that happened to be the empty-text logo anchor, the container walk could
land on the wrong line for company/location, most visibly whenever a real
card inserts a badge/status line ("Actively recruiting", "N school alumni",
"N connections", "Easy Apply", ...) - those got mistaken for the location
itself, so real Melbourne/Sydney jobs were coming out as
LOCATION_UNCONFIRMED and getting hidden.

Fixed by two structural changes, no positional line-index assumptions:
1. Group every anchor by job id first, then pick the anchor with the most
   lines of its OWN text (`_richest_anchor_lines`) - reliably the full-card
   anchor, never the logo/bare-title ones, across every real template
   sampled.
2. Within that anchor's lines, find the company/location by CONTENT, not
   position: the line containing the "Company · Location" middle-dot
   separator if one exists (checked among all lines after the title, not
   assumed to be the very next one), else fall back to "first non-badge
   line is company, the one after it is location only if it actually looks
   like a location" (`email_alert_parsing.looks_like_location`) - and if
   neither line looks like a location, leave it unset rather than guessing
   (fail closed - `location_service.normalize_location` is the single place
   that decides eligibility from whatever `location` ends up being).

Badge/status lines are recognised via one central classifier
(`_is_badge_or_status_line`) rather than scattered special-casing, so a
badge is filtered out wherever it appears (never mistaken for company or
location, never left dangling in the description snippet).

Never scrapes linkedin.com itself - this only ever reads the alert email
content already delivered to the user's own inbox.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from app.domain.enums import JobSourceType
from app.ingestion.email_alert_parsing import clean_lines, job_container, looks_like_location
from app.ingestion.job_source import RawJobPosting

_JOB_URL_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.IGNORECASE)
_COMPANY_LOCATION_SEPARATOR = "·"  # middle dot: "Company · Location"

# Pure UI chrome - never a title/company/location/snippet value.
_BOILERPLATE_TEXT = {"view job", "apply", "easy apply", "see job", "save"}

# Badge/status text real LinkedIn cards insert around the company/location
# line - centrally defined here rather than special-cased at each call site
# (see module docstring). Exact-match phrases plus a few count-style
# patterns ("41 school alumni", "3 connections", "Over 100 applicants").
_STATUS_BADGE_EXACT = {
    "actively recruiting",
    "promoted",
    "be an early applicant",
}
# "N school alumni" (plural) and "1 school alum" (singular, real LinkedIn
# phrasing for a count of exactly one) are both real variants.
_ALUMNI_RE = re.compile(r"^\d+\s+.*\balum(?:nus|na|ni)?\b", re.IGNORECASE)
_CONNECTIONS_RE = re.compile(r"^\d+\s+connections?$", re.IGNORECASE)
_APPLICANT_COUNT_RE = re.compile(r"\bapplicants?\b", re.IGNORECASE)


def _is_badge_or_status_line(line: str) -> bool:
    lowered = line.lower().strip()
    if lowered in _BOILERPLATE_TEXT or lowered in _STATUS_BADGE_EXACT:
        return True
    return bool(
        _ALUMNI_RE.match(line) or _CONNECTIONS_RE.match(line) or _APPLICANT_COUNT_RE.search(line)
    )


def _own_lines(anchor: Tag) -> list[str]:
    return [line for line in clean_lines(anchor) if not _is_badge_or_status_line(line)]


def _split_company_location(line: str) -> tuple[str, str | None]:
    if _COMPANY_LOCATION_SEPARATOR in line:
        company, _, location = line.partition(_COMPANY_LOCATION_SEPARATOR)
        company = company.strip()
        location = location.strip()
        return (company or "Unknown", location or None)
    return (line, None)


def _richest_anchor_lines(anchors: list[Tag]) -> list[str]:
    """The anchor carrying the most lines of its own text is reliably the
    full-card wrapper (title + company/location + badges) - the logo and
    bare-title duplicates that share the same job id never carry more.

    A real card's own text always covers title *and* company/location (>= 2
    lines after badges are filtered) - anything short of that (a bare title
    link, an empty image link) can't tell company/location apart on its own,
    so it falls back to the surrounding container, the same safety net the
    parser has always had for a title-only anchor with company/location as
    sibling elements."""
    candidates = [_own_lines(a) for a in anchors]
    richest = max(candidates, key=len, default=[])
    if len(richest) >= 2:
        return richest
    container_lines = [
        line
        for line in clean_lines(job_container(anchors[0]))
        if not _is_badge_or_status_line(line)
    ]
    return container_lines if len(container_lines) > len(richest) else richest


def _fields_from_lines(lines: list[str]) -> tuple[str, str, str | None, str] | None:
    if not lines:
        return None
    title = lines[0]
    rest = lines[1:]

    separator_line = next((line for line in rest if _COMPANY_LOCATION_SEPARATOR in line), None)
    if separator_line is not None:
        company, location = _split_company_location(separator_line)
        remaining = [line for line in rest if line != separator_line]
        return title, company, location, " ".join(remaining)

    # No "Company · Location" line - some templates put them on separate
    # lines instead. Company is the first remaining line; the line after it
    # is only trusted as a location if it actually looks like one (fail
    # closed per the module docstring - never invent a location).
    if not rest:
        return title, "Unknown", None, ""
    company = rest[0]
    location = rest[1] if len(rest) > 1 and looks_like_location(rest[1]) else None
    remaining = [line for line in rest[1:] if line != location]
    return title, company, location, " ".join(remaining)


def parse_linkedin_alert_email(
    html: str, *, message_id: str, received_at: datetime | None = None
) -> list[RawJobPosting]:
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Group every anchor by job id first (in document order) - a real card
    # is wrapped by several anchors sharing one id (logo, full card, bare
    # title), and which one happens to come first in the DOM is not a
    # reliable signal of which one carries the useful text (see module
    # docstring). This also guarantees one posting per job id regardless of
    # how many duplicate links point to it.
    anchors_by_job_id: dict[str, list[Tag]] = {}
    order: list[str] = []
    hrefs_by_job_id: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        match = _JOB_URL_RE.search(href)
        if not match:
            continue
        job_id = match.group(1)
        if job_id not in anchors_by_job_id:
            anchors_by_job_id[job_id] = []
            hrefs_by_job_id[job_id] = href
            order.append(job_id)
        anchors_by_job_id[job_id].append(anchor)

    postings: list[RawJobPosting] = []
    for job_id in order:
        fields = _fields_from_lines(_richest_anchor_lines(anchors_by_job_id[job_id]))
        if fields is None:
            continue
        title, company, location, snippet = fields
        if not title:
            continue

        postings.append(
            RawJobPosting(
                title=title,
                company=company,
                location=location,
                source_url=hrefs_by_job_id[job_id],
                source_type=JobSourceType.LINKEDIN,
                raw_description=snippet or title,
                external_id=job_id,
                published_at=received_at,
                retrieved_at=received_at,
                source_metadata={"gmail_message_id": message_id},
            )
        )

    return postings
