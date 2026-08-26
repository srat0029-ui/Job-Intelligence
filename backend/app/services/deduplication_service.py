"""Deterministic deduplication of discovered job postings.

No LLM involvement whatsoever - duplicates are detected with cheap,
explainable signals, checked in order of reliability:

1. Same source + same external_id (Adzuna gives every posting a stable id).
2. Same canonical URL (strips query strings/fragments/trailing slash).
3. Same normalised (company, title, location) triple.
4. Same description fingerprint (hash of normalised description text) -
   catches reposts under a different title/URL.

If none of these match, the posting is treated as new. Fuzzy/near-duplicate
matching (edit distance, embeddings) is explicitly out of scope for this
milestone - the interface below (`find_duplicate`) is the seam a future
similarity-based check would plug into without touching callers.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.discovery import DiscoveredJobModel
from app.ingestion.job_source import RawJobPosting

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def description_fingerprint(description: str) -> str:
    normalized = normalize_text(description)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_fingerprint(posting: RawJobPosting) -> str:
    """A single fingerprint combining the normalised (company, title,
    location) triple - used as a fallback signal when there's no external
    id or URL to match on (or as a defence against two different URLs for
    the same repost)."""
    parts = [
        normalize_text(posting.company),
        normalize_text(posting.title),
        normalize_text(posting.location),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def find_duplicate(db: Session, posting: RawJobPosting) -> DiscoveredJobModel | None:
    """Returns the existing DiscoveredJobModel this posting duplicates, if any."""
    # 1. Same source + external id.
    if posting.external_id:
        model = db.execute(
            select(DiscoveredJobModel).where(
                DiscoveredJobModel.source == posting.source_type.value,
                DiscoveredJobModel.external_id == posting.external_id,
            )
        ).scalar_one_or_none()
        if model is not None:
            return model

    # 2. Same canonical URL.
    url = canonical_url(posting.source_url)
    if url:
        candidates = db.execute(
            select(DiscoveredJobModel).where(DiscoveredJobModel.source_url.is_not(None))
        ).scalars()
        for candidate in candidates:
            if canonical_url(candidate.source_url) == url:
                return candidate

    # 3 & 4. Normalised (company, title, location) or description fingerprint.
    fingerprint = compute_fingerprint(posting)
    desc_fingerprint = description_fingerprint(posting.raw_description)
    model = db.execute(
        select(DiscoveredJobModel).where(
            (DiscoveredJobModel.dedupe_fingerprint == fingerprint)
            | (DiscoveredJobModel.description_fingerprint == desc_fingerprint)
        )
    ).scalar_one_or_none()
    return model
