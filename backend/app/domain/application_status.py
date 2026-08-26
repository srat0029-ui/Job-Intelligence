"""Domain model for the application-status audit trail.

Deliberately minimal: this milestone only tracks status the user records by
hand (Interested -> Applying -> Applied -> Interview -> ...). No automatic
applications, no writing to external systems - see app/services docs. The
history exists because outcome data (did this job lead to an interview?) is
what will eventually calibrate the scoring weights in a future milestone.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import ApplicationStatus


class ApplicationStatusEvent(BaseModel):
    id: UUID | None = None
    job_id: UUID
    status: ApplicationStatus
    note: str | None = None
    created_at: datetime | None = None
