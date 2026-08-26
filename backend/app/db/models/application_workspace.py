"""ORM model for the Application Workspace.

`job_id` is a real, unique FK to the existing `jobs` table (CASCADE) - one
workspace per job, no second job system.
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ApplicationWorkspaceModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "application_workspaces"

    job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
