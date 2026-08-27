"""Parses a SEEK job-alert email (HTML body) into individual RawJobPostings.

Uses BeautifulSoup (the brief explicitly asks for "robust HTML parsing
rather than regex-only" here) rather than the regex-based `html_text.py`
used for ATS description HTML - alert emails contain multiple, separately
structured job listings that need to be found and split apart, not just
stripped to plain text.

Honesty note (see the milestone report): built against a realistic
synthetic fixture, not a real SEEK template, since this session has no
inbox access. The anchor-based strategy (find every link to a job URL,
then read the surrounding block for title/company/location - see
email_alert_parsing.py) is deliberately template-agnostic so it degrades
gracefully rather than silently returning nothing if SEEK's real markup
differs in the details - but it will likely want a real-fixture tuning
pass once connected.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.domain.enums import JobSourceType
from app.ingestion.email_alert_parsing import clean_lines, job_container
from app.ingestion.job_source import RawJobPosting

_JOB_URL_RE = re.compile(r"seek\.com\.au/job/(\d+)", re.IGNORECASE)

# Boilerplate anchor/button text that is never itself a job title - skipped
# when picking which text represents the title.
_BOILERPLATE_TEXT = {
    "view job",
    "view this job",
    "apply now",
    "quick apply",
    "save job",
    "save this job",
    "see more",
}

_SALARY_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$?[\d,]+(?:\.\d+)?)?(?:\s*/?\s*\w+)?")


def parse_seek_alert_email(
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

        container = job_container(anchor)
        anchor_text = anchor.get_text(strip=True)
        lines = [
            line for line in clean_lines(container) if line.lower() not in _BOILERPLATE_TEXT
        ]

        title = (
            anchor_text
            if anchor_text and anchor_text.lower() not in _BOILERPLATE_TEXT
            else (lines[0] if lines else None)
        )
        if not title:
            continue

        remaining = [line for line in lines if line != title]
        salary_match = next((m for line in remaining if (m := _SALARY_RE.search(line))), None)
        salary_text = salary_match.group(0) if salary_match else None
        remaining_no_salary = [
            line for line in remaining if not (salary_match and salary_match.group(0) in line)
        ]

        company = remaining_no_salary[0] if len(remaining_no_salary) > 0 else "Unknown"
        location = remaining_no_salary[1] if len(remaining_no_salary) > 1 else None
        snippet = " ".join(remaining_no_salary[2:]) if len(remaining_no_salary) > 2 else ""

        metadata: dict = {"gmail_message_id": message_id}
        if salary_text:
            metadata["salary_text"] = salary_text

        postings.append(
            RawJobPosting(
                title=title,
                company=company,
                location=location,
                source_url=href,
                source_type=JobSourceType.SEEK,
                raw_description=snippet or title,
                external_id=job_id,
                published_at=received_at,
                retrieved_at=received_at,
                source_metadata=metadata,
            )
        )

    return postings
