"""Declarative base + shared column helpers for all ORM models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Float, Integer, MetaData, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# A fixed naming convention keeps Alembic autogenerate output stable and
# constraint names predictable across environments.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class GenerationMetaMixin:
    """Shared provenance/versioning columns for a generated application
    artefact (Milestone 4A) - version/status/prompt/model/cost/reviewer
    result, so every artefact type stores its audit trail identically
    rather than each table inventing its own shape. `created_at` (from
    TimestampMixin, used alongside this) doubles as the generation
    timestamp - no separate column needed."""

    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30))
    prompt_version: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reviewer_issues: Mapped[list] = mapped_column(JSONB, default=list)
    regeneration_attempt: Mapped[int] = mapped_column(Integer, default=1)
