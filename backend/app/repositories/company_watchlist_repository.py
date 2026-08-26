"""Data access for the target-company watchlist."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.company_watchlist import CompanyWatchlistModel
from app.domain.company_watchlist import CompanyWatchlistEntry
from app.domain.enums import ATSType, CompanyPriority


def _to_domain(model: CompanyWatchlistModel) -> CompanyWatchlistEntry:
    return CompanyWatchlistEntry(
        id=model.id,
        company_name=model.company_name,
        enabled=model.enabled,
        priority=CompanyPriority(model.priority),
        careers_url=model.careers_url,
        ats_type=ATSType(model.ats_type),
        ats_identifier=model.ats_identifier,
        preferred_locations=list(model.preferred_locations or []),
        notes=model.notes,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class CompanyWatchlistRepository:
    def create(self, db: Session, entry: CompanyWatchlistEntry) -> CompanyWatchlistEntry:
        model = CompanyWatchlistModel(
            company_name=entry.company_name,
            enabled=entry.enabled,
            priority=entry.priority.value,
            careers_url=entry.careers_url,
            ats_type=entry.ats_type.value,
            ats_identifier=entry.ats_identifier,
            preferred_locations=list(entry.preferred_locations),
            notes=entry.notes,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def update(
        self, db: Session, entry_id: UUID, entry: CompanyWatchlistEntry
    ) -> CompanyWatchlistEntry | None:
        model = db.get(CompanyWatchlistModel, entry_id)
        if model is None:
            return None
        model.company_name = entry.company_name
        model.enabled = entry.enabled
        model.priority = entry.priority.value
        model.careers_url = entry.careers_url
        model.ats_type = entry.ats_type.value
        model.ats_identifier = entry.ats_identifier
        model.preferred_locations = list(entry.preferred_locations)
        model.notes = entry.notes
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def delete(self, db: Session, entry_id: UUID) -> bool:
        model = db.get(CompanyWatchlistModel, entry_id)
        if model is None:
            return False
        db.delete(model)
        db.commit()
        return True

    def get(self, db: Session, entry_id: UUID) -> CompanyWatchlistEntry | None:
        model = db.get(CompanyWatchlistModel, entry_id)
        return _to_domain(model) if model else None

    def list_all(self, db: Session) -> list[CompanyWatchlistEntry]:
        models = (
            db.execute(
                select(CompanyWatchlistModel).order_by(CompanyWatchlistModel.company_name.asc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def list_enabled(self, db: Session) -> list[CompanyWatchlistEntry]:
        models = (
            db.execute(
                select(CompanyWatchlistModel).where(CompanyWatchlistModel.enabled.is_(True))
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
