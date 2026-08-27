"""Dev-only controlled validation sync for the SEEK tracking-link parser
fix.

Runs the SEEK alert messages already sitting in the connected Gmail inbox
through the real, unmodified `DiscoveryService` pipeline (dedup, geographic
eligibility, relevance pre-filter, cost-controlled AI analysis) so the fixed
parser can be validated end to end against real data - not just unit-tested
against synthetic fixtures.

Isolated to the email-alert source only: Adzuna is disabled and no company
watchlist/search-profile ids are matched, so this never triggers Adzuna/ATS
network calls. LinkedIn's own search still runs (JobAlertEmailSource always
checks both), but every LinkedIn message was already correctly processed by
the earlier real sync, so it's skipped by the normal watermark check - no
LinkedIn reprocessing happens.

Most of the target SEEK messages are already marked processed in
`processed_gmail_messages` from the earlier (broken) sync that extracted 0
jobs from each. `_ForceReprocessSeekRepository` below is a dev-only,
in-process wrapper that treats exactly those message ids as unseen for this
one run - `mark_processed` is a no-op for them (the row already exists and
`gmail_message_id` is UNIQUE) so the real watermark is left byte-for-byte as
it was; every other message id behaves through the real repository,
unchanged. Nothing here weakens watermark/duplicate protection permanently -
this wrapper only exists for the lifetime of this script.

Costs real AI money if auto_ai_analysis is enabled (respects the existing
max_ai_analyses_per_run / daily budget caps in AppSettings - see
discovery_service.py, unchanged here).

Usage:
    python scripts/run_seek_controlled_sync.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.ai.providers.factory import get_llm_provider  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.domain.company_watchlist import CompanyWatchlistEntry  # noqa: E402
from app.ingestion.gmail_client import GmailClient  # noqa: E402
from app.ingestion.job_alert_email_source import (  # noqa: E402
    SEEK_SENDER_DOMAINS,
    JobAlertEmailSource,
    _gmail_query,
)
from app.repositories.gmail_credential_repository import GmailCredentialRepository  # noqa: E402
from app.repositories.processed_gmail_message_repository import (  # noqa: E402
    ProcessedGmailMessageRepository,
)
from app.services.analysis_orchestrator import CandidateProfileMissingError  # noqa: E402
from app.services.discovery_service import DiscoveryService, NoSearchProfilesError  # noqa: E402
from app.services.gmail_auth_service import GmailAuthService  # noqa: E402

SEEK_LOOKBACK_DAYS = 90


class _ForceReprocessSeekRepository(ProcessedGmailMessageRepository):
    def __init__(self, force_ids: set[str]) -> None:
        self._force_ids = force_ids

    def is_processed(self, db: Session, gmail_message_id: str) -> bool:
        if gmail_message_id in self._force_ids:
            return False
        return super().is_processed(db, gmail_message_id)

    def mark_processed(
        self, db: Session, *, gmail_message_id: str, source_type: str, jobs_extracted: int
    ) -> None:
        if gmail_message_id in self._force_ids:
            return
        super().mark_processed(
            db,
            gmail_message_id=gmail_message_id,
            source_type=source_type,
            jobs_extracted=jobs_extracted,
        )


class _NoWatchlistRepository:
    def list_enabled(self, db: Session) -> list[CompanyWatchlistEntry]:
        return []


class _WidenedLookbackCredentialRepository(GmailCredentialRepository):
    """JobAlertEmailSource.fetch() searches from `credential.last_sync_at`
    (already recent, from the earlier real sync) - wrapping just the copy
    JobAlertEmailSource reads widens that window to SEEK_LOOKBACK_DAYS so
    the already-recognised older SEEK messages are actually searched for,
    without writing anything to the real credential row (DiscoveryService's
    own, unwrapped repository still performs the real `set_last_sync` write
    at the end of the run, which is accurate - a sync did just happen)."""

    def get(self, db: Session):  # type: ignore[override]
        credential = super().get(db)
        if credential is None:
            return None
        widened = datetime.now(UTC) - timedelta(days=SEEK_LOOKBACK_DAYS)
        return credential.model_copy(update={"last_sync_at": widened})


def _target_seek_message_ids(db: Session) -> set[str]:
    cred_repo = GmailCredentialRepository()
    auth = GmailAuthService()
    credential = cred_repo.get(db)
    if credential is None:
        raise SystemExit("Gmail is not connected.")

    refresh_token = auth.decrypt(credential.refresh_token_encrypted)
    access_token, _ = auth.refresh_access_token(refresh_token)
    client = GmailClient(access_token=access_token)
    lookback = datetime.now(UTC) - timedelta(days=SEEK_LOOKBACK_DAYS)
    query = _gmail_query(SEEK_SENDER_DOMAINS, after=lookback)
    return set(client.search_message_ids(query, max_results=100))


def main() -> int:
    db = SessionLocal()
    try:
        seek_ids = _target_seek_message_ids(db)
        print(f"Forcing reprocess of {len(seek_ids)} already-recognised SEEK message id(s)")
        forced_repo = _ForceReprocessSeekRepository(seek_ids)

        service = DiscoveryService(
            llm_provider=get_llm_provider(),
            company_watchlist_repository=_NoWatchlistRepository(),  # type: ignore[arg-type]
            adzuna_source_factory=lambda config: None,
            email_source_factory=lambda db: JobAlertEmailSource(
                db,
                processed_message_repository=forced_repo,
                credential_repository=_WidenedLookbackCredentialRepository(),
            ),
        )

        try:
            # A nonexistent search-profile id resolves to an empty profile
            # list (see DiscoveryService.run), so no Adzuna configs are ever
            # generated - this run is scoped to the email-alert source only.
            run = service.run(db, search_profile_ids=[uuid4()], triggered_by="seek_fix_validation")
        except CandidateProfileMissingError as exc:
            print(f"Cannot run: {exc}")
            return 1
        except NoSearchProfilesError as exc:
            print(f"Cannot run: {exc}")
            return 1

        c = run.counts
        print("SEEK-only controlled sync complete")
        print(f"  Status: {run.status.value}")
        print(f"  Sources used: {run.sources_used}")
        print(f"  Retrieved (raw postings): {c.retrieved}")
        print(f"  New (post-dedup): {c.new}")
        print(f"  Duplicates: {c.duplicates}")
        print(f"  Pre-filter rejected (geo + relevance): {c.prefilter_rejected}")
        print(f"  Eligible (awaiting/analysed): {c.eligible}")
        print(f"  AI analysed: {c.analysed}")
        print(f"  Deferred (run/budget limit): {c.deferred}")
        print(f"  Failed: {c.failed}")
        print(f"  Strong Apply+: {c.strong_apply_or_better}")
        print(f"  AI calls: {c.ai_calls}")
        print(f"  Estimated AI cost: ${run.estimated_cost_usd:.4f}")
        if run.error_message:
            print(f"  Error: {run.error_message}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
