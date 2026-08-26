"""Adzuna (Australia) job source.

Only real external job-board integration in this milestone. Deliberately
conservative about call volume: one HTTP request per (location, page), using
Adzuna's `what_or` parameter to OR-match every configured keyword in a
single query rather than issuing one request per keyword - a search profile
with 8 keyword variants and 3 locations is 3 requests per page, not 24.

Failure handling is per-request: a bad page/location stops paging for that
location and logs a warning, but never raises out of `fetch()` - one flaky
page must not take down an entire discovery run (see DiscoveryService).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.domain.enums import JobSourceType
from app.ingestion.job_source import JobSource, RawJobPosting

logger = get_logger(__name__)

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaSearchConfig(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    results_per_page: int = Field(default=50, ge=1, le=50)
    max_pages: int = Field(default=1, ge=1, le=10)
    max_days_old: int | None = Field(default=None, ge=1)


class AdzunaJobSource(JobSource):
    source_type = JobSourceType.ADZUNA

    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        config: AdzunaSearchConfig,
        country: str = "au",
        client: httpx.Client | None = None,
    ) -> None:
        if not app_id or not app_key:
            raise ValueError(
                "Adzuna requires both app_id and app_key - check ADZUNA_APP_ID/ADZUNA_APP_KEY."
            )
        self._app_id = app_id
        self._app_key = app_key
        self._config = config
        self._country = country
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=20.0)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self) -> list[RawJobPosting]:
        postings: list[RawJobPosting] = []
        seen_external_ids: set[str] = set()
        locations: list[str | None] = list(self._config.locations) or [None]

        for location in locations:
            for page in range(1, self._config.max_pages + 1):
                try:
                    response = self._request(page=page, location=location)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "adzuna_request_failed", location=location, page=page, error=str(exc)
                    )
                    break

                if response.status_code == 429:
                    logger.warning("adzuna_rate_limited", location=location, page=page)
                    break
                if response.status_code >= 400:
                    logger.warning(
                        "adzuna_http_error",
                        location=location,
                        page=page,
                        status=response.status_code,
                    )
                    break

                try:
                    data = response.json()
                except ValueError:
                    logger.warning("adzuna_malformed_json", location=location, page=page)
                    break

                results = data.get("results")
                if not results:
                    break  # no more results for this location - stop paging it

                for raw in results:
                    posting = self._normalize(raw)
                    if posting is None:
                        continue
                    if posting.external_id:
                        if posting.external_id in seen_external_ids:
                            continue
                        seen_external_ids.add(posting.external_id)
                    postings.append(posting)

        return postings

    def _request(self, *, page: int, location: str | None) -> httpx.Response:
        params: dict[str, str | int] = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "results_per_page": self._config.results_per_page,
            "content-type": "application/json",
        }
        if self._config.keywords:
            params["what_or"] = " ".join(self._config.keywords)
        if location:
            params["where"] = location
        if self._config.max_days_old:
            params["max_days_old"] = self._config.max_days_old

        url = f"{ADZUNA_BASE_URL}/{self._country}/search/{page}"
        return self._client.get(url, params=params)

    def _normalize(self, raw: dict) -> RawJobPosting | None:
        """Maps one Adzuna result object into the canonical RawJobPosting.

        Returns None (rather than raising) for a malformed entry missing a
        field we can't sensibly default - one bad record must not abort the
        whole page.
        """
        try:
            title = raw["title"]
            description = raw["description"]
        except (KeyError, TypeError):
            keys = list(raw.keys()) if isinstance(raw, dict) else None
            logger.warning("adzuna_skipped_malformed_result", raw_keys=keys)
            return None

        company = (raw.get("company") or {}).get("display_name") or "Unknown"
        location_obj = raw.get("location") or {}
        location = location_obj.get("display_name")
        category = (raw.get("category") or {}).get("label")

        published_at = None
        created_raw = raw.get("created")
        if created_raw:
            try:
                published_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            except ValueError:
                published_at = None

        return RawJobPosting(
            title=title,
            company=company,
            location=location,
            source_url=raw.get("redirect_url"),
            source_type=self.source_type,
            raw_description=description,
            external_id=str(raw.get("id")) if raw.get("id") is not None else None,
            salary_min=raw.get("salary_min"),
            salary_max=raw.get("salary_max"),
            currency=raw.get("salary_currency") or "AUD",
            employment_type=raw.get("contract_time") or raw.get("contract_type"),
            published_at=published_at,
            retrieved_at=datetime.now(UTC),
            source_metadata={
                k: v
                for k, v in {
                    "adzuna_category": category,
                    "adzuna_contract_type": raw.get("contract_type"),
                }.items()
                if v is not None
            },
        )
