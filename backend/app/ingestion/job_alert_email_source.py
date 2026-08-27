"""`JobSource` for SEEK/LinkedIn job-alert emails - the primary discovery
path (see the milestone plan). Reads the connected Gmail inbox read-only,
recognises SEEK/LinkedIn alert senders, parses each unseen message into
individual `RawJobPosting`s, and never touches message state (no read/
archive/label/delete - see gmail_client.py).

Recognised senders are plain per-source config here, not buried logic, so
adding a third alert source later is one new entry, not a control-flow
change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import JobSourceType
from app.ingestion.gmail_client import GmailClient, GmailMessage
from app.ingestion.job_source import JobSource, RawJobPosting
from app.ingestion.linkedin_email_parser import parse_linkedin_alert_email
from app.ingestion.seek_email_parser import parse_seek_alert_email
from app.repositories.gmail_credential_repository import GmailCredentialRepository
from app.repositories.processed_gmail_message_repository import ProcessedGmailMessageRepository
from app.services.gmail_auth_service import GmailAuthService

logger = get_logger(__name__)

# Domain-level match against the message's From header - generous on
# purpose (any address at these domains is treated as a recognised alert
# sender) since the exact sending address varies and can change without
# notice; narrowed further by requiring the message to actually parse into
# at least one job before it counts for anything.
SEEK_SENDER_DOMAINS = ["seek.com.au", "seek.com"]
LINKEDIN_SENDER_DOMAINS = ["linkedin.com"]

DEFAULT_LOOKBACK_DAYS = 7


def _gmail_query(domains: list[str], *, after: datetime) -> str:
    sender_clause = " OR ".join(f"from:{domain}" for domain in domains)
    epoch = int(after.timestamp())
    return f"({sender_clause}) after:{epoch}"


def _sender_matches(sender: str, domains: list[str]) -> bool:
    lowered = sender.lower()
    return any(domain in lowered for domain in domains)


class GmailNotConnectedError(Exception):
    pass


class JobAlertEmailSource(JobSource):
    """Not tied to one `JobSourceType` at the class level - each returned
    `RawJobPosting` carries its own correct type (SEEK or LinkedIn) since a
    single sync can see both."""

    source_type = JobSourceType.EMAIL

    def __init__(
        self,
        db: Session,
        *,
        credential_repository: GmailCredentialRepository | None = None,
        processed_message_repository: ProcessedGmailMessageRepository | None = None,
        auth_service: GmailAuthService | None = None,
        gmail_client_factory=None,
    ) -> None:
        self._db = db
        self._credential_repository = credential_repository or GmailCredentialRepository()
        self._processed_message_repository = (
            processed_message_repository or ProcessedGmailMessageRepository()
        )
        self._auth_service = auth_service or GmailAuthService()
        # Testing seam - see tests/unit/test_job_alert_email_source.py.
        self._gmail_client_factory = gmail_client_factory or (
            lambda token: GmailClient(access_token=token)
        )

    def _get_access_token(self) -> str:
        credential = self._credential_repository.get(self._db)
        if credential is None:
            raise GmailNotConnectedError("Gmail is not connected.")

        now = datetime.now(UTC)
        expires_at = credential.access_token_expires_at
        if (
            credential.access_token_encrypted
            and expires_at is not None
            and expires_at.replace(tzinfo=UTC) > now + timedelta(minutes=2)
        ):
            return self._auth_service.decrypt(credential.access_token_encrypted)

        refresh_token = self._auth_service.decrypt(credential.refresh_token_encrypted)
        access_token, new_expires_at = self._auth_service.refresh_access_token(refresh_token)
        self._credential_repository.set_access_token(
            self._db,
            access_token_encrypted=self._auth_service.encrypt(access_token),
            expires_at=new_expires_at,
        )
        return access_token

    def fetch(self) -> list[RawJobPosting]:
        credential = self._credential_repository.get(self._db)
        if credential is None:
            return []

        access_token = self._get_access_token()
        client = self._gmail_client_factory(access_token)

        lookback = credential.last_sync_at or (
            datetime.now(UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        )
        postings: list[RawJobPosting] = []

        for domains, source_type, parser in (
            (SEEK_SENDER_DOMAINS, JobSourceType.SEEK, parse_seek_alert_email),
            (LINKEDIN_SENDER_DOMAINS, JobSourceType.LINKEDIN, parse_linkedin_alert_email),
        ):
            try:
                message_ids = client.search_message_ids(_gmail_query(domains, after=lookback))
            except Exception as exc:  # noqa: BLE001 - one source's failure must not stop the other
                logger.warning("gmail_search_failed", source=source_type.value, error=str(exc))
                continue

            for message_id in message_ids:
                if self._processed_message_repository.is_processed(self._db, message_id):
                    continue
                try:
                    message: GmailMessage = client.get_message(message_id)
                except Exception as exc:  # noqa: BLE001 - one bad message must not stop the sync
                    logger.warning(
                        "gmail_fetch_message_failed", message_id=message_id, error=str(exc)
                    )
                    continue

                if not _sender_matches(message.sender, domains) or not message.html_body:
                    self._processed_message_repository.mark_processed(
                        self._db,
                        gmail_message_id=message_id,
                        source_type=source_type.value,
                        jobs_extracted=0,
                    )
                    continue

                parsed = parser(
                    message.html_body,
                    message_id=message_id,
                    received_at=message.received_at,
                )
                postings.extend(parsed)
                self._processed_message_repository.mark_processed(
                    self._db,
                    gmail_message_id=message_id,
                    source_type=source_type.value,
                    jobs_extracted=len(parsed),
                )

        return postings
