"""Unit tests for GreenhouseJobSource - mocked HTTP only, mirrors
test_lever_source.py's coverage."""

from __future__ import annotations

import httpx
import pytest

from app.domain.enums import JobSourceType
from app.ingestion.greenhouse_source import GreenhouseJobSource


def _job(job_id: int, title: str = "Graduate Software Engineer") -> dict:
    return {
        "id": job_id,
        "title": title,
        "location": {"name": "Sydney, Australia"},
        "content": "<p>Join our engineering team.</p><ul><li>Python</li><li>SQL</li></ul>",
        "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{job_id}",
        "updated_at": "2026-01-10T00:00:00+00:00",
        "departments": [{"name": "Engineering"}],
    }


def _source(handler, max_postings: int = 100) -> GreenhouseJobSource:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return GreenhouseJobSource(
        board_token="acme", company_name="Acme", max_postings=max_postings, client=client
    )


def test_normalizes_a_successful_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [_job(1), _job(2)]})

    postings = _source(handler).fetch()

    assert len(postings) == 2
    assert postings[0].title == "Graduate Software Engineer"
    assert postings[0].company == "Acme"
    assert postings[0].location == "Sydney, Australia"
    assert postings[0].source_type == JobSourceType.GREENHOUSE
    assert postings[0].external_id == "1"
    assert postings[0].source_url == "https://boards.greenhouse.io/acme/jobs/1"
    assert "Python" in postings[0].raw_description
    assert postings[0].source_metadata.get("greenhouse_departments") == ["Engineering"]


def test_respects_max_postings_cap():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [_job(i) for i in range(10)]})

    postings = _source(handler, max_postings=3).fetch()
    assert len(postings) == 3


def test_skips_malformed_results_without_failing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [{"title": "Missing id"}, _job(2)]})

    postings = _source(handler).fetch()
    assert len(postings) == 1
    assert postings[0].external_id == "2"


def test_unknown_board_raises_lookup_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(LookupError):
        _source(handler).fetch()


def test_rate_limit_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    with pytest.raises(TimeoutError):
        _source(handler).fetch()


def test_server_error_raises_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(ConnectionError):
        _source(handler).fetch()


def test_unexpected_shape_returns_empty_list_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "the expected shape"})

    postings = _source(handler).fetch()
    assert postings == []


def test_missing_board_token_raises_at_construction_time():
    with pytest.raises(ValueError):
        GreenhouseJobSource(board_token="")
