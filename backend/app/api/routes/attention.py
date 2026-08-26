"""Internal attention/notification endpoints (no email/push - see
app/services/attention_service.py)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_attention_service, get_db
from app.domain.attention import AttentionItem
from app.services.attention_service import AttentionService

router = APIRouter(prefix="/api/attention", tags=["attention"])


@router.get("", response_model=list[AttentionItem])
def list_attention_items(
    db: Session = Depends(get_db),
    service: AttentionService = Depends(get_attention_service),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AttentionItem]:
    return service.list_recent(db, unread_only=unread_only, limit=limit)


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db), service: AttentionService = Depends(get_attention_service)
) -> dict[str, int]:
    return {"unread_count": service.count_unread(db)}


@router.put("/{item_id}/read", response_model=AttentionItem)
def mark_attention_item_read(
    item_id: UUID,
    db: Session = Depends(get_db),
    service: AttentionService = Depends(get_attention_service),
) -> AttentionItem:
    item = service.mark_read(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Attention item not found")
    return item
