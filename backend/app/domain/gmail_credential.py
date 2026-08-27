"""Domain model for the single stored Gmail OAuth credential.

Deliberately its own model/table/repository, never folded into
`AppSettings` - `AppSettings` is serialised wholesale to the frontend via
`GET /api/discovery/settings`, and keeping the (encrypted) refresh token in
a completely separate model makes "this can never accidentally ride along
in an unrelated API response" true by construction, not by remembering to
exclude a field.

Single-user app: one row, exactly like `AppSettings`/`Candidate`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GmailCredential(BaseModel):
    connected_email: str
    refresh_token_encrypted: str
    access_token_encrypted: str | None = None
    access_token_expires_at: datetime | None = None
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None  # "ok" | "error"
    last_sync_message: str | None = None
