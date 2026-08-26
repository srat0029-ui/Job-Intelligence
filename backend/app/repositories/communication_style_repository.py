"""Data access for the singleton communication-style row.

Lazily created on first read/write - same pattern as AppSettingsRepository.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.communication_style import CommunicationStyleModel
from app.domain.communication_style import CommunicationStyle


def _to_domain(model: CommunicationStyleModel) -> CommunicationStyle:
    return CommunicationStyle(
        tone=model.tone,
        avoid_buzzwords=model.avoid_buzzwords,
        avoid_exaggerated_claims=model.avoid_exaggerated_claims,
        prefer_specific_examples=model.prefer_specific_examples,
        avoid_em_dashes=model.avoid_em_dashes,
        region_convention=model.region_convention,
    )


class CommunicationStyleRepository:
    def _get_or_create_model(self, db: Session) -> CommunicationStyleModel:
        model = db.query(CommunicationStyleModel).first()
        if model is None:
            model = CommunicationStyleModel()
            db.add(model)
            db.commit()
            db.refresh(model)
        return model

    def get(self, db: Session) -> CommunicationStyle:
        return _to_domain(self._get_or_create_model(db))

    def update(self, db: Session, style: CommunicationStyle) -> CommunicationStyle:
        model = self._get_or_create_model(db)
        model.tone = style.tone
        model.avoid_buzzwords = style.avoid_buzzwords
        model.avoid_exaggerated_claims = style.avoid_exaggerated_claims
        model.prefer_specific_examples = style.prefer_specific_examples
        model.avoid_em_dashes = style.avoid_em_dashes
        model.region_convention = style.region_convention
        db.commit()
        db.refresh(model)
        return _to_domain(model)
