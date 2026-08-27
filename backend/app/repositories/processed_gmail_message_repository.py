"""Tracks which Gmail message IDs have already been ingested, so the same
alert email is never re-parsed - see app/db/models/gmail_credential.py's
`ProcessedGmailMessageModel` docstring."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.gmail_credential import ProcessedGmailMessageModel


class ProcessedGmailMessageRepository:
    def is_processed(self, db: Session, gmail_message_id: str) -> bool:
        return (
            db.query(ProcessedGmailMessageModel)
            .filter(ProcessedGmailMessageModel.gmail_message_id == gmail_message_id)
            .first()
            is not None
        )

    def mark_processed(
        self, db: Session, *, gmail_message_id: str, source_type: str, jobs_extracted: int
    ) -> None:
        model = ProcessedGmailMessageModel(
            gmail_message_id=gmail_message_id,
            source_type=source_type,
            processed_at=datetime.now(UTC),
            jobs_extracted=jobs_extracted,
        )
        db.add(model)
        db.commit()
