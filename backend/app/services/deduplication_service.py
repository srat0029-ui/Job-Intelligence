"""Multi-stage deduplication of discovered job postings.

No LLM involvement at any stage - duplicates are detected with cheap,
explainable signals, checked in order of reliability. Once a canonical
`DiscoveredJob` exists for a real posting, every subsequent sighting of it
(from the same source re-fetched, or a different source entirely) becomes a
`SourceObservation` linked to that one canonical row - nothing is ever
discarded, and the canonical row's presentation fields (source/URL/company/
title) can be "promoted" to a more authoritative source without touching
its identity or history. See `app/db/models/discovery.py`.

STAGE 1 - exact identifiers (checked against every past *observation*, not
just each canonical row's own current fields, precisely because a
canonical row's fields may have been promoted away from the source that's
being re-checked):
  - same source + external_id
  - same canonical URL (query string/fragment/trailing slash stripped)

STAGE 2 - deterministic fingerprints (checked against canonical rows):
  - same normalised (company, title, location) triple
  - same description fingerprint (hash of normalised description text)

STAGE 3 - fuzzy similarity, only reached if stages 1-2 found nothing, and
only compared against a BOUNDED candidate set (same normalised company,
published within a date window) - never an unbounded scan of the table.
Requires the company to match as a hard gate (never merges across
companies); combines title-token and description-token Jaccard similarity
(word-level, not character-level - a posting reworded/reordered between an
aggregator and a direct listing keeps most of its vocabulary even when
sentence structure changes, which a character-diff ratio would
underestimate) into one confidence score, weighted so description content
- typically copied near-verbatim between sources even when the title is
rebranded ("Graduate Data Scientist" vs "2027 Graduate Program - Data
Science") - dominates. Below `AUTO_MERGE_THRESHOLD`, nothing is merged -
per the brief, an uncertain match is a false negative (two separate
opportunities), never a risky auto-merge. No LLM is involved in any of
this. See tests/unit/test_fuzzy_deduplication.py for the calibration
cases these constants are tuned against.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.discovery import DiscoveredJobModel, SourceObservationModel
from app.domain.enums import DuplicateMatchStage, JobSourceType
from app.ingestion.job_source import RawJobPosting

_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "of", "for", "and", "in", "at", "to", "with", "our", "on", "we", "you",
    "is", "are", "will", "using", "your", "as", "be", "this", "that", "from", "or", "who",
    "program", "role",
}

# Direct-employer ATS postings outrank a syndicated aggregator listing for
# the same job - see app/services/deduplication_service.py::maybe_promote_canonical_fields.
SOURCE_QUALITY_RANK: dict[str, int] = {
    JobSourceType.MANUAL.value: 0,
    JobSourceType.ADZUNA.value: 1,
    JobSourceType.LEVER.value: 2,
    JobSourceType.GREENHOUSE.value: 2,
}

TITLE_SIMILARITY_WEIGHT = 0.15
DESCRIPTION_SIMILARITY_WEIGHT = 0.70
DATE_PROXIMITY_WEIGHT = 0.15

AUTO_MERGE_THRESHOLD = 0.60
MIN_TITLE_TOKEN_SIMILARITY = 0.15
FUZZY_CANDIDATE_DATE_WINDOW_DAYS = 21
FUZZY_DESCRIPTION_TOKEN_LIMIT = 400  # cap tokenisation cost on long descriptions


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def _word_tokens(text: str, limit: int | None = None) -> set[str]:
    words = _TOKEN_RE.findall(text.lower())
    if limit is not None:
        words = words[:limit]
    return {t for t in words if len(t) > 1} - _STOPWORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


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


@dataclass
class ExactMatch:
    model: DiscoveredJobModel
    stage: DuplicateMatchStage


def find_exact_or_fingerprint_duplicate(db: Session, posting: RawJobPosting) -> ExactMatch | None:
    """Stages 1-2. Returns the canonical DiscoveredJobModel this posting
    duplicates (with which stage matched, for the observation audit trail),
    if any exact/deterministic match exists."""
    if posting.external_id:
        obs = (
            db.execute(
                select(SourceObservationModel).where(
                    SourceObservationModel.source == posting.source_type.value,
                    SourceObservationModel.external_id == posting.external_id,
                )
            )
            .scalars()
            .first()
        )
        if obs is not None:
            model = db.get(DiscoveredJobModel, obs.discovered_job_id)
            if model is not None:
                return ExactMatch(model=model, stage=DuplicateMatchStage.EXACT_ID)

    url = canonical_url(posting.source_url)
    if url:
        observations = db.execute(
            select(SourceObservationModel).where(SourceObservationModel.source_url.is_not(None))
        ).scalars()
        for obs in observations:
            if canonical_url(obs.source_url) == url:
                model = db.get(DiscoveredJobModel, obs.discovered_job_id)
                if model is not None:
                    return ExactMatch(model=model, stage=DuplicateMatchStage.CANONICAL_URL)

    fingerprint = compute_fingerprint(posting)
    desc_fingerprint = description_fingerprint(posting.raw_description)
    model = db.execute(
        select(DiscoveredJobModel).where(
            (DiscoveredJobModel.dedupe_fingerprint == fingerprint)
            | (DiscoveredJobModel.description_fingerprint == desc_fingerprint)
        )
    ).scalar_one_or_none()
    if model is not None:
        return ExactMatch(model=model, stage=DuplicateMatchStage.DETERMINISTIC_FINGERPRINT)
    return None


@dataclass
class FuzzyMatch:
    model: DiscoveredJobModel
    confidence: float
    reason: str


def find_fuzzy_duplicate(db: Session, posting: RawJobPosting) -> FuzzyMatch | None:
    """Stage 3. Only ever compares against a bounded candidate set (same
    normalised company, published within FUZZY_CANDIDATE_DATE_WINDOW_DAYS)
    - never an unbounded O(n^2) scan. Returns None (a false negative) unless
    confidence clears AUTO_MERGE_THRESHOLD."""
    normalized_company = normalize_text(posting.company)
    if not normalized_company:
        return None

    candidates_stmt = select(DiscoveredJobModel).where(
        DiscoveredJobModel.company.ilike(posting.company)
    )
    reference_date = posting.published_at or posting.retrieved_at
    if reference_date is not None:
        # Compare as naive (UTC by convention) - Postgres round-trips
        # DateTime columns as naive, so an aware `reference_date` here would
        # otherwise silently rely on the driver's implicit tz handling.
        naive_reference = reference_date.replace(tzinfo=None)
        window_start = naive_reference - timedelta(days=FUZZY_CANDIDATE_DATE_WINDOW_DAYS)
        window_end = naive_reference + timedelta(days=FUZZY_CANDIDATE_DATE_WINDOW_DAYS)
        candidates_stmt = candidates_stmt.where(
            (DiscoveredJobModel.published_at.is_(None))
            | (DiscoveredJobModel.published_at.between(window_start, window_end))
        )

    candidates = db.execute(candidates_stmt).scalars().all()
    if not candidates:
        return None

    posting_title_tokens = _word_tokens(posting.title)
    posting_desc_tokens = _word_tokens(posting.raw_description, limit=FUZZY_DESCRIPTION_TOKEN_LIMIT)

    best: FuzzyMatch | None = None
    for candidate in candidates:
        if normalize_text(candidate.company) != normalized_company:
            continue  # hard gate - never merge across companies, regardless of similarity

        title_similarity = _jaccard(posting_title_tokens, _word_tokens(candidate.title))
        if title_similarity < MIN_TITLE_TOKEN_SIMILARITY:
            continue  # unrelated titles - never merge even if descriptions coincidentally overlap

        candidate_desc_tokens = _word_tokens(
            candidate.raw_description, limit=FUZZY_DESCRIPTION_TOKEN_LIMIT
        )
        description_similarity = _jaccard(posting_desc_tokens, candidate_desc_tokens)

        date_bonus = 0.0
        if reference_date is not None and candidate.published_at is not None:
            # Postgres round-trips DateTime columns as naive (UTC by
            # convention throughout this app), while a freshly-fetched
            # posting's published_at is usually timezone-aware - strip
            # tzinfo from both sides before subtracting so this never
            # raises on an aware/naive mismatch.
            naive_ref = reference_date.replace(tzinfo=None)
            naive_candidate = candidate.published_at.replace(tzinfo=None)
            days_apart = abs((naive_ref - naive_candidate).days)
            date_bonus = max(0.0, 1.0 - days_apart / FUZZY_CANDIDATE_DATE_WINDOW_DAYS)

        confidence = (
            TITLE_SIMILARITY_WEIGHT * title_similarity
            + DESCRIPTION_SIMILARITY_WEIGHT * description_similarity
            + DATE_PROXIMITY_WEIGHT * date_bonus
        )
        if confidence < AUTO_MERGE_THRESHOLD:
            continue
        if best is None or confidence > best.confidence:
            reason = (
                f"same company + {title_similarity:.2f} title similarity + "
                f"{description_similarity:.2f} description similarity"
            )
            best = FuzzyMatch(model=candidate, confidence=round(confidence, 3), reason=reason)

    return best


def maybe_promote_canonical_fields(model: DiscoveredJobModel, posting: RawJobPosting) -> bool:
    """If `posting` comes from a more authoritative source than the
    canonical row's current source, promote the row's presentation/
    navigation fields (source, external_id, URL, company, title) to match
    it - never touches fit-affecting fields (description, location, salary,
    ...) or anything already computed from them. Returns True if promoted."""
    current_rank = SOURCE_QUALITY_RANK.get(model.source, 0)
    new_rank = SOURCE_QUALITY_RANK.get(posting.source_type.value, 0)
    if new_rank <= current_rank:
        return False

    model.source = posting.source_type.value
    model.external_id = posting.external_id
    model.source_url = posting.source_url
    model.company = posting.company
    model.title = posting.title
    return True
