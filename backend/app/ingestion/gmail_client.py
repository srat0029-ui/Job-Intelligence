"""Thin, read-only Gmail REST API client.

Only ever calls `messages.list` (search) and `messages.get` (fetch) - never
`.modify`/`.trash`/`.batchDelete`/`.import`, so nothing here can mark a
message read, archive it, label it, or delete it. See gmail_auth_service.py
for why this is raw httpx rather than google-api-python-client.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailMessage(BaseModel):
    message_id: str
    sender: str
    subject: str
    received_at: datetime | None
    html_body: str | None


class GmailApiError(Exception):
    pass


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _find_html_part(payload: dict) -> str | None:
    """Depth-first search through a Gmail message payload's MIME tree for
    the first text/html part - alert emails are near-universally
    multipart/alternative (plain text + HTML), and the HTML part is what
    the SEEK/LinkedIn parsers need."""
    mime_type = payload.get("mimeType", "")
    body_data = (payload.get("body") or {}).get("data")
    if mime_type == "text/html" and body_data:
        return _decode_base64url(body_data)
    for part in payload.get("parts") or []:
        found = _find_html_part(part)
        if found is not None:
            return found
    return None


def _header(headers: list[dict], name: str) -> str | None:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


class GmailClient:
    def __init__(self, *, access_token: str, client: httpx.Client | None = None) -> None:
        self._access_token = access_token
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=20.0)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def search_message_ids(self, query: str, *, max_results: int = 50) -> list[str]:
        response = self._client.get(
            f"{GMAIL_API_BASE}/messages",
            headers=self._headers(),
            params={"q": query, "maxResults": max_results},
        )
        if response.status_code >= 400:
            raise GmailApiError(f"Gmail search failed ({response.status_code}): {response.text}")
        data = response.json()
        return [m["id"] for m in data.get("messages", [])]

    def get_message(self, message_id: str) -> GmailMessage:
        response = self._client.get(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            headers=self._headers(),
            params={"format": "full"},
        )
        if response.status_code >= 400:
            raise GmailApiError(f"Gmail fetch failed ({response.status_code}): {response.text}")
        data = response.json()
        payload = data.get("payload", {})
        headers = payload.get("headers", [])

        received_at = None
        internal_date = data.get("internalDate")
        if internal_date:
            try:
                received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
            except (ValueError, OverflowError):
                received_at = None

        return GmailMessage(
            message_id=data["id"],
            sender=_header(headers, "From") or "",
            subject=_header(headers, "Subject") or "",
            received_at=received_at,
            html_body=_find_html_part(payload),
        )
