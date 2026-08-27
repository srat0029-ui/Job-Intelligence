"""Unit tests for GmailClient - all HTTP calls are mocked via
httpx.MockTransport (same style as test_adzuna_source.py), so these never
hit the real network/credentials."""

from __future__ import annotations

import base64

import httpx
import pytest

from app.ingestion.gmail_client import GmailApiError, GmailClient


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _client(handler) -> GmailClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return GmailClient(access_token="fake-token", client=http_client)


def test_search_message_ids_returns_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "messages" in str(request.url)
        return httpx.Response(200, json={"messages": [{"id": "abc"}, {"id": "def"}]})

    client = _client(handler)
    assert client.search_message_ids("from:seek.com.au") == ["abc", "def"]


def test_search_message_ids_empty_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _client(handler)
    assert client.search_message_ids("from:nowhere") == []


def test_search_message_ids_error_raises_gmail_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = _client(handler)
    with pytest.raises(GmailApiError):
        client.search_message_ids("from:seek.com.au")


def test_get_message_parses_html_part_and_headers():
    html = "<html><body><a href='https://seek.com.au/job/1'>Job</a></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg-1",
                "internalDate": "1700000000000",
                "payload": {
                    "mimeType": "multipart/alternative",
                    "headers": [
                        {"name": "From", "value": "SEEK Alerts <jobmail@seek.com.au>"},
                        {"name": "Subject", "value": "New jobs for you"},
                    ],
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _b64url("plain text")}},
                        {"mimeType": "text/html", "body": {"data": _b64url(html)}},
                    ],
                },
            },
        )

    client = _client(handler)
    message = client.get_message("msg-1")

    assert message.message_id == "msg-1"
    assert message.sender == "SEEK Alerts <jobmail@seek.com.au>"
    assert message.subject == "New jobs for you"
    assert message.html_body == html
    assert message.received_at is not None


def test_get_message_with_no_html_part_returns_none_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg-2",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": _b64url("plain only")},
                    "headers": [],
                },
            },
        )

    client = _client(handler)
    message = client.get_message("msg-2")
    assert message.html_body is None


def test_get_message_error_raises_gmail_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client = _client(handler)
    with pytest.raises(GmailApiError):
        client.get_message("msg-3")
