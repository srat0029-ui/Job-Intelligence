"""ORM model for the target-company watchlist (see
app/domain/company_watchlist.py)."""

from sqlalchemy import ARRAY, Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CompanyWatchlistModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "company_watchlist"
    __table_args__ = (
        UniqueConstraint("ats_type", "ats_identifier", name="uq_company_watchlist_ats"),
    )

    company_name: Mapped[str] = mapped_column(String(300))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    careers_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ats_type: Mapped[str] = mapped_column(String(30))
    ats_identifier: Mapped[str] = mapped_column(String(200))
    preferred_locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
