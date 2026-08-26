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

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS_RE = re.compile(r"</(p|div|li|br|h[1-6]|ul|ol)\s*>", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    with_breaks = _BLOCK_TAGS_RE.sub("\n", value)
    text = _TAG_RE.sub("", with_breaks)
    text = html_module.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()
