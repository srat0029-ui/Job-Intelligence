"""Parses a LinkedIn job-alert email (HTML body) into individual
RawJobPostings. Same anchor-based, template-agnostic strategy as
seek_email_parser.py (shared via email_alert_parsing.py).

Calibrated against a real LinkedIn alert email (Part 25's live sync): each
job anchor wraps its own nested table, with the title in one cell and
"Company · Location" (joined by U+00B7 MIDDLE DOT) in the next - using the
anchor's own `clean_lines()` (rather than flat `get_text()`, which
concatenates every nested cell with no separating space) is what correctly
isolates the title from the company/location line.

Never scrapes linkedin.com itself - this only ever reads the alert email
content already delivered to the user's own inbox.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.domain.enums import JobSourceType
from app.ingestion.email_alert_parsing import clean_lines, job_container
from app.ingestion.job_source import RawJobPosting

_JOB_URL_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.IGNORECASE)
_BOILERPLATE_TEXT = {"view job", "apply", "easy apply", "see job", "save"}
_COMPANY_LOCATION_SEPARATOR = "·"  # middle dot: "Company · Location"


def _split_company_location(line: str) -> tuple[str, str | None]:
    if _COMPANY_LOCATION_SEPARATOR in line:
        company, _, location = line.partition(_COMPANY_LOCATION_SEPARATOR)
        company = company.strip()
        location = location.strip()
        return (company or "Unknown", location or None)
    return (line, None)


def parse_linkedin_alert_email(
    html: str, *, message_id: str, received_at: datetime | None = None
) -> list[RawJobPosting]:
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    postings: list[RawJobPosting] = []
    seen_job_ids: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        match = _JOB_URL_RE.search(href)
        if not match:
            continue
        job_id = match.group(1)
        if job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)

        # Prefer the anchor's own line-by-line breakdown (correctly
        # separates a nested title cell from a nested company/location
        # cell); fall back to the wider container only if the anchor itself
        # carries no structured text (a bare text-only "View job" link).
        anchor_lines = [
            line for line in clean_lines(anchor) if line.lower() not in _BOILERPLATE_TEXT
        ]
        container_lines = [
            line
            for line in clean_lines(job_container(anchor))
            if line.lower() not in _BOILERPLATE_TEXT
        ]
        lines = anchor_lines or container_lines

        title = lines[0] if lines else None
        if not title:
            continue

        remaining = [line for line in container_lines if line != title]
        company, location = _split_company_location(remaining[0]) if remaining else (
            "Unknown",
            None,
        )
        snippet = " ".join(remaining[1:]) if len(remaining) > 1 else ""

        postings.append(
            RawJobPosting(
                title=title,
                company=company,
                location=location,
                source_url=href,
                source_type=JobSourceType.LINKEDIN,
                raw_description=snippet or title,
                external_id=job_id,
                published_at=received_at,
                retrieved_at=received_at,
                source_metadata={"gmail_message_id": message_id},
            )
        )

    return postings
