"""ORM model for the candidate's application writing-style preferences.

Single-row table, same pattern as AppSettingsModel - see
app/services/communication_style_service.py for lazy singleton creation.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CommunicationStyleModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "communication_styles"

    tone: Mapped[str] = mapped_column(String(50), default="conversational_professional")
    avoid_buzzwords: Mapped[bool] = mapped_column(Boolean, default=True)
    avoid_exaggerated_claims: Mapped[bool] = mapped_column(Boolean, default=True)
    prefer_specific_examples: Mapped[bool] = mapped_column(Boolean, default=True)
    avoid_em_dashes: Mapped[bool] = mapped_column(Boolean, default=True)
    region_convention: Mapped[str] = mapped_column(String(50), default="australian")
