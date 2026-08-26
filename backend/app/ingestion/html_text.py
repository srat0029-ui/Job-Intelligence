"""Minimal HTML-to-plain-text conversion for ATS job descriptions.

Lever/Greenhouse both return description content as HTML. A regex-based
strip is not a general-purpose HTML parser, but it's enough to turn ATS
description markup into readable plain text for extraction/matching - full
DOM parsing (e.g. BeautifulSoup) would be a real dependency for a problem
this constrained.
"""

from __future__ import annotations

import html as html_module
import re
from datetime import datetime

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS_RE = re.compile(r"</(p|div|li|br|h[1-6]|ul|ol)\s*>", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def extract_title(html: str | None) -> str | None:
    """Best-effort `<title>` extraction for research-source provenance."""
    if not html:
        return None
    match = _TITLE_RE.search(html)
    if not match:
        return None
    title = html_module.unescape(_WHITESPACE_RE.sub(" ", match.group(1))).strip()
    return title or None


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    with_breaks = _BLOCK_TAGS_RE.sub("\n", value)
    text = _TAG_RE.sub("", with_breaks)
    text = html_module.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


_PUBLISHED_META_RES = [
    re.compile(r'property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'content=["\']([^"\']+)["\']\s+property=["\']article:published_time["\']', re.I),
    re.compile(r'name=["\']date["\']\s+content=["\']([^"\']+)["\']', re.I),
]


def extract_published_at(html: str | None) -> datetime | None:
    """Best-effort publish-date extraction from common meta tags, so
    research-claim freshness checks (see CompanyResearchService) have
    something to work with for news/press-release sources. Returns None
    (never a guess) when no recognised tag is present - freshness checks
    simply skip a source whose date can't be determined."""
    if not html:
        return None
    for pattern in _PUBLISHED_META_RES:
        match = pattern.search(html)
        if not match:
            continue
        raw = match.group(1).strip()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def strip_html_for_research(value: str | None) -> str:
    """Like `strip_html`, but also drops <script>/<style> block *contents*.

    Lever/Greenhouse description HTML never contains these, so the plain
    `strip_html` above doesn't bother; a generic company web page fetched
    for research routinely does, and leaving injected JS/CSS text in would
    pollute what gets handed to research-claim synthesis and grounding
    checks.
    """
    if not value:
        return ""
    return strip_html(_SCRIPT_STYLE_RE.sub(" ", value))
