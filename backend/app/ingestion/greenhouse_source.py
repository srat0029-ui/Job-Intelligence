"""Greenhouse job source - operates against one configured CompanyWatchlist
entry, same company-scoped pattern as LeverJobSource.

Uses Greenhouse's public job board API:
`GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
- a long-documented, public, unauthenticated endpoint intended for
embedding a company's job board (the same data Greenhouse's own careers
widget uses), not a privileged employer/recruiting API. If a board token is
misconfigured or the board is private, this returns 404 and the adapter
fails closed for that one company (see PART 5's "don't guess, don't
require privileged credentials" instruction) - it never falls back to
guessing a different endpoint shape.

Like Lever, there is no pagination in the public boards API (one response
returns the full current job list) and nothing here ever applies to a job.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.logging import get_logger
from app.domain.enums import JobSourceType
from app.ingestion.html_text import strip_html
from app.ingestion.job_source import JobSource, RawJobPosting

logger = get_logger(__name__)

GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseJobSource(JobSource):
    source_type = JobSourceType.GREENHOUSE

    def __init__(
        self,
        *,
        board_token: str,
        company_name: str | None = None,
        max_postings: int = 100,
        client: httpx.Client | None = None,
    ) -> None:
        if not board_token:
            raise ValueError(
                "Greenhouse requires a board token (CompanyWatchlistEntry.ats_identifier)."
            )
        self._board_token = board_token
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
                f"{GREENHOUSE_BASE_URL}/{self._board_token}/jobs", params={"content": "true"}
            )
        except httpx.HTTPError as exc:
            logger.warning("greenhouse_request_failed", board=self._board_token, error=str(exc))
            raise

        if response.status_code == 404:
            logger.warning("greenhouse_unknown_board", board=self._board_token)
            raise LookupError(f"Unknown Greenhouse board: {self._board_token}")
        if response.status_code == 429:
            logger.warning("greenhouse_rate_limited", board=self._board_token)
            raise TimeoutError(f"Greenhouse rate-limited for board: {self._board_token}")
        if response.status_code >= 400:
            logger.warning(
                "greenhouse_http_error", board=self._board_token, status=response.status_code
            )
            raise ConnectionError(
                f"Greenhouse HTTP {response.status_code} for board: {self._board_token}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("greenhouse_malformed_json", board=self._board_token)
            raise ValueError(
                f"Greenhouse returned malformed JSON for board: {self._board_token}"
            ) from exc

        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            logger.warning("greenhouse_unexpected_shape", board=self._board_token)
            return []

        postings: list[RawJobPosting] = []
        for raw in jobs[: self._max_postings]:
            posting = self._normalize(raw)
            if posting is not None:
                postings.append(posting)
        return postings

    def _normalize(self, raw: dict) -> RawJobPosting | None:
        if not isinstance(raw, dict):
            return None
        try:
            title = raw["title"]
            job_id = raw["id"]
        except (KeyError, TypeError):
            logger.warning("greenhouse_skipped_malformed_result", board=self._board_token)
            return None

        location = (raw.get("location") or {}).get("name")
        description = strip_html(raw.get("content") or "")
        if not description:
            return None

        departments = raw.get("departments") or []
        department_names = [
            d.get("name") for d in departments if isinstance(d, dict) and d.get("name")
        ]

        published_at = None
        updated_at_raw = raw.get("updated_at") or raw.get("first_published")
        if updated_at_raw:
            try:
                published_at = datetime.fromisoformat(str(updated_at_raw).replace("Z", "+00:00"))
            except ValueError:
                published_at = None

        return RawJobPosting(
            title=title,
            company=self._company_name or self._board_token,
            location=location,
            source_url=raw.get("absolute_url"),
            source_type=self.source_type,
            raw_description=description,
            external_id=str(job_id),
            published_at=published_at,
            retrieved_at=datetime.now(UTC),
            source_metadata={
                k: v
                for k, v in {"greenhouse_departments": department_names or None}.items()
                if v is not None
            },
        )
