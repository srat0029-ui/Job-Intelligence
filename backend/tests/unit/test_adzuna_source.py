"""Unit tests for AdzunaJobSource - all HTTP calls are mocked via
httpx.MockTransport, so these never hit the real network/credentials."""

from __future__ import annotations

import httpx
import pytest

from app.domain.enums import JobSourceType
from app.ingestion.adzuna_source import AdzunaJobSource, AdzunaSearchConfig


def _job(job_id: int, title: str = "Graduate Data Scientist") -> dict:
    return {
        "id": job_id,
        "title": title,
        "description": "A great job description.",
        "company": {"display_name": "Acme Corp"},
        "location": {"display_name": "Melbourne, VIC"},
        "redirect_url": f"https://example.com/jobs/{job_id}",
        "salary_min": 70000,
        "salary_max": 90000,
        "salary_currency": "AUD",
        "contract_time": "full_time",
        "created": "2026-08-20T10:00:00Z",
        "category": {"label": "IT Jobs"},
    }


def _source(handler, **config_overrides) -> AdzunaJobSource:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    config = AdzunaSearchConfig(
        keywords=["data scientist"], locations=["Melbourne"], **config_overrides
    )
    return AdzunaJobSource(app_id="id", app_key="key", config=config, client=client)


def test_normalizes_a_successful_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [_job(1), _job(2)]})

    source = _source(handler)
    postings = source.fetch()

    assert len(postings) == 2
    assert postings[0].title == "Graduate Data Scientist"
    assert postings[0].company == "Acme Corp"
    assert postings[0].location == "Melbourne, VIC"
    assert postings[0].source_type == JobSourceType.ADZUNA
    assert postings[0].external_id == "1"
    assert postings[0].salary_min == 70000
    assert postings[0].source_metadata.get("adzuna_category") == "IT Jobs"


def test_stops_paging_when_a_page_returns_no_results():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.path.rsplit("/", 1)[-1]
        calls.append(page)
        if page == "1":
            return httpx.Response(200, json={"results": [_job(1)]})
        return httpx.Response(200, json={"results": []})

    source = _source(handler, max_pages=5)
    postings = source.fetch()

    assert len(postings) == 1
    assert calls == ["1", "2"]  # stopped after the empty page, didn't fetch pages 3-5


def test_deduplicates_repeated_external_ids_within_one_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [_job(1), _job(1)]})

    source = _source(handler)
    postings = source.fetch()

    assert len(postings) == 1


def test_skips_malformed_results_without_failing_the_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"title": "Missing description"}, _job(2)]},
        )

    source = _source(handler)
    postings = source.fetch()

    assert len(postings) == 1
    assert postings[0].external_id == "2"


def test_http_error_stops_paging_that_location_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    source = _source(handler)
    postings = source.fetch()  # must not raise

    assert postings == []


def test_rate_limit_stops_paging_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    source = _source(handler)
    postings = source.fetch()

    assert postings == []


def test_malformed_json_response_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    source = _source(handler)
    postings = source.fetch()

    assert postings == []


def test_connection_failure_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    source = _source(handler)
    postings = source.fetch()

    assert postings == []


def test_multiple_locations_each_get_their_own_query():
    seen_locations = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_locations.append(request.url.params.get("where"))
        return httpx.Response(200, json={"results": [_job(len(seen_locations))]})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    config = AdzunaSearchConfig(keywords=["data scientist"], locations=["Melbourne", "Hobart"])
    source = AdzunaJobSource(app_id="id", app_key="key", config=config, client=client)

    postings = source.fetch()

    assert seen_locations == ["Melbourne", "Hobart"]
    assert len(postings) == 2


def test_keywords_are_combined_with_what_or_not_one_call_per_keyword():
    requests_made = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_made.append(request)
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    config = AdzunaSearchConfig(
        keywords=["graduate data scientist", "junior data scientist", "data analyst"],
        locations=["Melbourne"],
    )
    source = AdzunaJobSource(app_id="id", app_key="key", config=config, client=client)
    source.fetch()

    assert len(requests_made) == 1  # one request for the one location, not one per keyword
    assert requests_made[0].url.params.get("what_or") == (
        "graduate data scientist junior data scientist data analyst"
    )


def test_missing_credentials_raises_at_construction_time():
    with pytest.raises(ValueError):
        AdzunaJobSource(app_id="", app_key="", config=AdzunaSearchConfig())
