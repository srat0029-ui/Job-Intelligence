"""Data access for the internal attention/notification system."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.attention import AttentionItemModel
from app.domain.attention import AttentionItem
from app.domain.enums import AttentionItemStatus, AttentionItemType


def _to_domain(model: AttentionItemModel) -> AttentionItem:
    return AttentionItem(
        id=model.id,
        item_type=AttentionItemType(model.item_type),
        title=model.title,
        message=model.message,
        related_discovered_job_id=model.related_discovered_job_id,
        related_job_id=model.related_job_id,
        related_company=model.related_company,
        status=AttentionItemStatus(model.status),
        created_at=model.created_at,
    )


class AttentionRepository:
    def create(self, db: Session, item: AttentionItem) -> AttentionItem:
        model = AttentionItemModel(
            item_type=item.item_type.value,
            title=item.title,
            message=item.message,
            related_discovered_job_id=item.related_discovered_job_id,
            related_job_id=item.related_job_id,
            related_company=item.related_company,
            status=item.status.value,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def list_recent(
        self, db: Session, *, unread_only: bool = False, limit: int = 50
    ) -> list[AttentionItem]:
        stmt = (
            select(AttentionItemModel).order_by(AttentionItemModel.created_at.desc()).limit(limit)
        )
        if unread_only:
            stmt = stmt.where(AttentionItemModel.status == AttentionItemStatus.UNREAD.value)
        models = db.execute(stmt).scalars().all()
        return [_to_domain(m) for m in models]

    def count_unread(self, db: Session) -> int:
        return db.execute(
            select(func.count()).where(
                AttentionItemModel.status == AttentionItemStatus.UNREAD.value
            )
        ).scalar_one()

    def mark_read(self, db: Session, item_id: UUID) -> AttentionItem | None:
        model = db.get(AttentionItemModel, item_id)
        if model is None:
            return None
        model.status = AttentionItemStatus.READ.value
        db.commit()
        db.refresh(model)
        return _to_domain(model)
