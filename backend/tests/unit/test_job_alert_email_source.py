"""Unit tests for JobAlertEmailSource's orchestration: dispatch to the
right parser by sender, skipping already-processed Gmail messages, and
behaving correctly when Gmail isn't connected. Uses fake auth/gmail-client
seams (matching test_discovery_service.py's fake-JobSource style) so these
never touch the real network or encryption."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.gmail_credential import GmailCredential
from app.ingestion.gmail_client import GmailMessage
from app.ingestion.job_alert_email_source import JobAlertEmailSource
from app.repositories.gmail_credential_repository import GmailCredentialRepository
from app.repositories.processed_gmail_message_repository import ProcessedGmailMessageRepository


class _FakeAuthService:
    """Treats tokens as already "decrypted" (identity) - these tests care
    about dispatch/watermark/skip behaviour, not encryption."""

    def decrypt(self, value: str) -> str:
        return value

    def encrypt(self, value: str) -> str:
        return value

    def refresh_access_token(self, refresh_token: str):
        raise AssertionError("refresh_access_token should not be called - token isn't expired")


class _FakeGmailClient:
    def __init__(self, *, messages_by_query: dict[str, list[GmailMessage]]) -> None:
        self._messages_by_query = messages_by_query

    def search_message_ids(self, query: str) -> list[str]:
        for key, messages in self._messages_by_query.items():
            if key in query:
                return [m.message_id for m in messages]
        return []

    def get_message(self, message_id: str) -> GmailMessage:
        for messages in self._messages_by_query.values():
            for message in messages:
                if message.message_id == message_id:
                    return message
        raise AssertionError(f"unexpected message_id {message_id}")


def _connect_gmail(db) -> None:
    GmailCredentialRepository().save(
        db,
        GmailCredential(
            connected_email="me@example.com",
            refresh_token_encrypted="refresh-token",
            access_token_encrypted="access-token",
            access_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
            connected_at=datetime.now(UTC),
        ),
    )


_SEEK_HTML = (
    "<table><tr><td>"
    '<a href="https://www.seek.com.au/job/777">Graduate Software Engineer</a>'
    "<div>Acme</div><div>Melbourne VIC</div>"
    "</td></tr></table>"
)
_LINKEDIN_HTML = (
    "<table><tr><td>"
    '<a href="https://www.linkedin.com/jobs/view/888">Associate AI Engineer</a>'
    "<div>TechCo</div><div>Sydney NSW</div>"
    "</td></tr></table>"
)


def _source(db, client) -> JobAlertEmailSource:
    return JobAlertEmailSource(
        db,
        auth_service=_FakeAuthService(),
        gmail_client_factory=lambda token: client,
    )


def test_returns_empty_when_gmail_not_connected(db):
    client = _FakeGmailClient(messages_by_query={})
    source = _source(db, client)
    assert source.fetch() == []


def test_dispatches_seek_and_linkedin_messages_to_the_right_parser(db):
    _connect_gmail(db)
    client = _FakeGmailClient(
        messages_by_query={
            "seek.com.au": [
                GmailMessage(
                    message_id="seek-1",
                    sender="SEEK <jobmail@seek.com.au>",
                    subject="New jobs",
                    received_at=datetime.now(UTC),
                    html_body=_SEEK_HTML,
                )
            ],
            "linkedin.com": [
                GmailMessage(
                    message_id="li-1",
                    sender="LinkedIn Job Alerts <jobs-noreply@linkedin.com>",
                    subject="New jobs",
                    received_at=datetime.now(UTC),
                    html_body=_LINKEDIN_HTML,
                )
            ],
        }
    )
    source = _source(db, client)
    postings = source.fetch()

    titles = {p.title for p in postings}
    assert titles == {"Graduate Software Engineer", "Associate AI Engineer"}


def test_already_processed_message_is_never_reparsed(db):
    _connect_gmail(db)
    ProcessedGmailMessageRepository().mark_processed(
        db, gmail_message_id="seek-1", source_type="seek", jobs_extracted=1
    )
    client = _FakeGmailClient(
        messages_by_query={
            "seek.com.au": [
                GmailMessage(
                    message_id="seek-1",
                    sender="SEEK <jobmail@seek.com.au>",
                    subject="New jobs",
                    received_at=datetime.now(UTC),
                    html_body=_SEEK_HTML,
                )
            ]
        }
    )
    source = _source(db, client)
    assert source.fetch() == []


def test_watermark_defaults_to_lookback_window_when_never_synced(db):
    """A never-synced credential should search from a bounded lookback
    window, not an unbounded "since forever" query."""
    _connect_gmail(db)
    seen_queries: list[str] = []

    class _RecordingClient(_FakeGmailClient):
        def search_message_ids(self, query: str) -> list[str]:
            seen_queries.append(query)
            return super().search_message_ids(query)

    source = _source(db, _RecordingClient(messages_by_query={}))
    source.fetch()

    assert len(seen_queries) == 2  # one search per recognised source
    for query in seen_queries:
        assert "after:" in query


def test_message_from_unrecognised_sender_is_marked_processed_and_skipped(db):
    _connect_gmail(db)
    client = _FakeGmailClient(
        messages_by_query={
            "seek.com.au": [
                GmailMessage(
                    message_id="spoofed-1",
                    sender="someone@example.com",
                    subject="Not really SEEK",
                    received_at=datetime.now(UTC),
                    html_body=_SEEK_HTML,
                )
            ]
        }
    )
    source = _source(db, client)
    assert source.fetch() == []
    assert ProcessedGmailMessageRepository().is_processed(db, "spoofed-1")
