"""Domain model for the internal attention/notification system.

Deliberately internal-only for now (no email/push) - see
app/services/attention_service.py. `related_discovered_job_id` /
`related_job_id` / `related_company` are all optional so an item can point
at whatever's relevant (a specific job, a company, or nothing at all for a
source-health item).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import AttentionItemStatus, AttentionItemType


class AttentionItem(BaseModel):
    id: UUID | None = None
    item_type: AttentionItemType
    title: str
    message: str
    related_discovered_job_id: UUID | None = None
    related_job_id: UUID | None = None
    related_company: str | None = None
    status: AttentionItemStatus = AttentionItemStatus.UNREAD
    created_at: datetime | None = None
