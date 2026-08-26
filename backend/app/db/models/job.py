"""ORM model for job postings (raw, user- or adapter-supplied input)."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class JobModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "jobs"

    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="manual")
    raw_description: Mapped[str] = mapped_column(Text)
    application_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
