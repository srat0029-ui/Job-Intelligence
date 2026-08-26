"""Lever job source - operates against one configured CompanyWatchlist
entry, not a global search.

Lever is company/site-scoped: there is no "search all of Lever" endpoint,
only "list this one company's published postings" - `GET
https://api.lever.co/v0/postings/{site}?mode=json`, a documented, public,
unauthenticated endpoint (no privileged employer credentials involved; it's
the same data Lever's own embeddable careers-page widget uses). Each
`LeverJobSource` instance is therefore constructed for exactly one
`CompanyWatchlistEntry`, and `DiscoveryService` builds one instance per
enabled Lever watchlist entry - see PART 3/4 of the milestone brief for why
this is intentionally NOT folded into the generic discovery orchestrator.

No pagination exists in Lever's public API (it returns the full current
posting list in one response) and there is no application/apply
functionality used here at all - `applyUrl`/`hostedUrl` are captured purely
as read-only metadata for the user to open manually.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.logging import get_logger
from app.domain.enums import JobSourceType
from app.ingestion.html_text import strip_html
from app.ingestion.job_source import JobSource, RawJobPosting

logger = get_logger(__name__)

LEVER_BASE_URL = "https://api.lever.co/v0/postings"


class LeverJobSource(JobSource):
    source_type = JobSourceType.LEVER

    def __init__(
        self,
        *,
        site: str,
        company_name: str | None = None,
        max_postings: int = 100,
        client: httpx.Client | None = None,
    ) -> None:
        if not site:
            raise ValueError("Lever requires a site slug (CompanyWatchlistEntry.ats_identifier).")
        self._site = site
        self._company_name = company_name
        self._max_postings = max_postings
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=15.0)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> list[RawJobPosting]:
        try:
            response = self._client.get(
                f"{LEVER_BASE_URL}/{self._site}", params={"mode": "json"}
            )
        except httpx.HTTPError as exc:
            logger.warning("lever_request_failed", site=self._site, error=str(exc))
            raise

        if response.status_code == 404:
            logger.warning("lever_unknown_site", site=self._site)
            raise LookupError(f"Unknown Lever site: {self._site}")
        if response.status_code == 429:
            logger.warning("lever_rate_limited", site=self._site)
            raise TimeoutError(f"Lever rate-limited for site: {self._site}")
        if response.status_code >= 400:
            logger.warning("lever_http_error", site=self._site, status=response.status_code)
            raise ConnectionError(f"Lever HTTP {response.status_code} for site: {self._site}")

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("lever_malformed_json", site=self._site)
            raise ValueError(f"Lever returned malformed JSON for site: {self._site}") from exc

        if not isinstance(data, list):
            logger.warning("lever_unexpected_shape", site=self._site)
            return []

        postings: list[RawJobPosting] = []
        for raw in data[: self._max_postings]:
            posting = self._normalize(raw)
            if posting is not None:
                postings.append(posting)
        return postings

    def _normalize(self, raw: dict) -> RawJobPosting | None:
        if not isinstance(raw, dict):
            return None
        try:
            title = raw["text"]
            posting_id = raw["id"]
        except (KeyError, TypeError):
            logger.warning("lever_skipped_malformed_result", site=self._site)
            return None

        categories = raw.get("categories") or {}
        location = categories.get("location")
        team = categories.get("team")
        commitment = categories.get("commitment")
        workplace_type = raw.get("workplaceType")

        description_html = raw.get("descriptionPlain") or raw.get("description") or ""
        lists = raw.get("lists") or []
        list_text = "\n\n".join(
            f"{item.get('text', '')}\n" + strip_html(item.get("content", ""))
            for item in lists
            if isinstance(item, dict)
        )
        full_description = "\n\n".join(
            part for part in [strip_html(description_html), list_text] if part
        )
        if not full_description:
            return None

        published_at = None
        created_at_ms = raw.get("createdAt")
        if isinstance(created_at_ms, (int, float)):
            try:
                published_at = datetime.fromtimestamp(created_at_ms / 1000, tz=UTC)
            except (ValueError, OSError):
                published_at = None

        return RawJobPosting(
            title=title,
            company=self._company_name or self._site,
            location=location,
            source_url=raw.get("hostedUrl"),
            source_type=self.source_type,
            raw_description=full_description,
            external_id=str(posting_id),
            remote_type="remote" if workplace_type == "remote" else None,
            employment_type=commitment,
            published_at=published_at,
            retrieved_at=datetime.now(UTC),
            source_metadata={
                k: v
                for k, v in {
                    "lever_team": team,
                    "lever_apply_url": raw.get("applyUrl"),
                    "lever_workplace_type": workplace_type,
                }.items()
                if v is not None
            },
        )
