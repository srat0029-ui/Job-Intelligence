"""Unit tests for LeverJobSource - all HTTP calls are mocked via
httpx.MockTransport, so these never hit the real network."""

from __future__ import annotations

import httpx
import pytest

from app.domain.enums import JobSourceType
from app.ingestion.lever_source import LeverJobSource


def _posting(posting_id: str, title: str = "Graduate Data Scientist") -> dict:
    return {
        "id": posting_id,
        "text": title,
        "categories": {
            "location": "Melbourne, Australia",
            "team": "Data",
            "commitment": "Full-time",
        },
        "workplaceType": "hybrid",
        "hostedUrl": f"https://jobs.lever.co/acme/{posting_id}",
        "applyUrl": f"https://jobs.lever.co/acme/{posting_id}/apply",
        "createdAt": 1735689600000,  # 2025-01-01T00:00:00Z in ms
        "descriptionPlain": "Join our data team and build ML models.",
        "lists": [{"text": "Requirements", "content": "<ul><li>Python</li></ul>"}],
    }


def _source(handler, max_postings: int = 100) -> LeverJobSource:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return LeverJobSource(
        site="acme", company_name="Acme", max_postings=max_postings, client=client
    )


def test_normalizes_a_successful_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_posting("1"), _posting("2")])

    postings = _source(handler).fetch()

    assert len(postings) == 2
    assert postings[0].title == "Graduate Data Scientist"
    assert postings[0].company == "Acme"
    assert postings[0].location == "Melbourne, Australia"
    assert postings[0].source_type == JobSourceType.LEVER
    assert postings[0].external_id == "1"
    assert postings[0].source_url == "https://jobs.lever.co/acme/1"
    assert "Python" in postings[0].raw_description
    assert postings[0].remote_type is None  # workplaceType was "hybrid", not "remote"
    assert postings[0].source_metadata.get("lever_apply_url") == "https://jobs.lever.co/acme/1/apply"


def test_remote_workplace_type_is_normalised():
    def handler(request: httpx.Request) -> httpx.Response:
        posting = _posting("1")
        posting["workplaceType"] = "remote"
        return httpx.Response(200, json=[posting])

    postings = _source(handler).fetch()
    assert postings[0].remote_type == "remote"


def test_respects_max_postings_cap():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_posting(str(i)) for i in range(10)])

    postings = _source(handler, max_postings=3).fetch()
    assert len(postings) == 3


def test_skips_malformed_results_without_failing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"text": "Missing id"}, _posting("2")])

    postings = _source(handler).fetch()
    assert len(postings) == 1
    assert postings[0].external_id == "2"


def test_unknown_site_raises_lookup_error():
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


def test_malformed_json_raises_value_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(ValueError):
        _source(handler).fetch()


def test_unexpected_shape_returns_empty_list_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    postings = _source(handler).fetch()
    assert postings == []


def test_network_failure_propagates_as_httpx_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(httpx.HTTPError):
        _source(handler).fetch()


def test_missing_site_raises_at_construction_time():
    with pytest.raises(ValueError):
        LeverJobSource(site="")
