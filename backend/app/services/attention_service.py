"""Internal attention/notification system.

No email/push here - `AttentionItem` rows are surfaced only inside the app
(Dashboard). The abstraction (a typed, timestamped, read/unread item with
an optional link to a job/company) is deliberately channel-agnostic so a
future notifier (email/push) could subscribe to the same
`AttentionService.create_*` calls without this service changing.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.attention import AttentionItem
from app.domain.enums import AttentionItemType
from app.repositories.attention_repository import AttentionRepository


class AttentionService:
    def __init__(self, repository: AttentionRepository | None = None) -> None:
        self._repository = repository or AttentionRepository()

    def notify_high_priority_job(
        self,
        db: Session,
        *,
        discovered_job_id: UUID,
        job_title: str,
        company: str,
        priority: str,
    ) -> AttentionItem:
        return self._repository.create(
            db,
            AttentionItem(
                item_type=AttentionItemType.HIGH_PRIORITY_JOB,
                title=f"New {priority.replace('_', ' ').title()}: {job_title}",
                message=(
                    f"{job_title} at {company} scored high enough to be "
                    f"{priority.replace('_', ' ')}."
                ),
                related_discovered_job_id=discovered_job_id,
                related_company=company,
            ),
        )

    def notify_watchlist_posting(
        self, db: Session, *, discovered_job_id: UUID, job_title: str, company: str
    ) -> AttentionItem:
        return self._repository.create(
            db,
            AttentionItem(
                item_type=AttentionItemType.WATCHLIST_COMPANY_POSTING,
                title=f"{company} posted a new relevant role",
                message=f"{company} (on your watchlist) posted: {job_title}.",
                related_discovered_job_id=discovered_job_id,
                related_company=company,
            ),
        )

    def notify_analysis_failures(
        self, db: Session, *, failed_count: int, discovery_run_id: UUID
    ) -> AttentionItem:
        return self._repository.create(
            db,
            AttentionItem(
                item_type=AttentionItemType.ANALYSIS_FAILURES,
                title=f"{failed_count} job analyses failed",
                message=(
                    f"{failed_count} job(s) failed AI analysis in discovery run "
                    f"{discovery_run_id}. Check the run detail for error categories."
                ),
            ),
        )

    def notify_source_unhealthy(
        self, db: Session, *, source_key: str, consecutive_failures: int
    ) -> AttentionItem:
        return self._repository.create(
            db,
            AttentionItem(
                item_type=AttentionItemType.SOURCE_UNHEALTHY,
                title=f"Source unhealthy: {source_key}",
                message=(
                    f"{source_key} has failed {consecutive_failures} runs in a row - "
                    "check Settings/Companies for details."
                ),
            ),
        )

    def list_recent(
        self, db: Session, *, unread_only: bool = False, limit: int = 50
    ) -> list[AttentionItem]:
        return self._repository.list_recent(db, unread_only=unread_only, limit=limit)

    def count_unread(self, db: Session) -> int:
        return self._repository.count_unread(db)

    def mark_read(self, db: Session, item_id: UUID) -> AttentionItem | None:
        return self._repository.mark_read(db, item_id)
