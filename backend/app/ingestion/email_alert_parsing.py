"""Shared HTML-block extraction helpers for job-alert email parsers
(seek_email_parser.py, linkedin_email_parser.py) - the anchor-based
"find every link to a job URL, then read its surrounding block" strategy
is identical between sources; only the job-URL pattern and a handful of
boilerplate phrases differ."""

from __future__ import annotations

import re

from bs4 import Tag

from app.services.location_service import AU_CITIES, AU_STATE_ABBREVIATIONS, FOREIGN_CITIES

# Zero-width characters some real alert templates insert inside text (e.g.
# SEEK's "Applied on 1​9​ ​Aug" date) - almost certainly a
# scraper-deterrent, but it also breaks naive keyword matching downstream if
# left in, so it's stripped as part of basic text hygiene.
_ZERO_WIDTH_RE = re.compile(r"[​‌‍﻿]")

# A light "does this text plausibly name a place" signal - NOT geographic
# classification (that stays exactly once, in location_service.normalize_
# location; a parser only needs to know which extracted line to *hand* it,
# never what country/eligibility it implies). Reuses location_service's own
# AU/foreign reference data rather than a second hand-maintained list.
_LOCATION_MARKER_RE = re.compile(r"\((?:hybrid|remote|onsite)\)|\bremote\b", re.IGNORECASE)
_AU_STATE_WORD_RE = re.compile(r"\b(?:" + "|".join(AU_STATE_ABBREVIATIONS.values()) + r")\b")
_KNOWN_CITY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(c) for c in {**AU_CITIES, **FOREIGN_CITIES}) + r")\b",
    re.IGNORECASE,
)


def looks_like_location(line: str) -> bool:
    return bool(
        _LOCATION_MARKER_RE.search(line)
        or _AU_STATE_WORD_RE.search(line)
        or _KNOWN_CITY_RE.search(line)
    )


def clean_lines(container: Tag) -> list[str]:
    """Every distinct, non-boilerplate, non-empty line of text within a
    container, in document order - the raw material for guessing which
    line is the company vs. the location vs. a snippet."""
    lines: list[str] = []
    for text in container.stripped_strings:
        cleaned = _ZERO_WIDTH_RE.sub("", text).strip()
        if not cleaned or cleaned in lines:
            continue
        lines.append(cleaned)
    return lines


def job_container(anchor: Tag) -> Tag:
    """Walks up to a reasonably-sized ancestor block likely to contain the
    rest of this one job's details (company/location/snippet) without also
    pulling in neighbouring jobs - bounded so a malformed/deeply-nested
    email can't cause runaway ancestor walking."""
    node: Tag = anchor
    for _ in range(4):
        parent = node.parent
        if parent is None or not isinstance(parent, Tag):
            break
        # A <tr>/<table> boundary is a strong signal we've reached one
        # listing's own row in typical email-table layouts - stop there
        # rather than climbing into a container shared by multiple jobs.
        if parent.name in ("tr", "table"):
            return parent
        node = parent
    return node
