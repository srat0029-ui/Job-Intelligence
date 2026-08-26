"""Data access for saved search profiles."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.discovery import SearchProfileModel
from app.domain.discovery import SearchProfile
from app.domain.enums import SeniorityLevel


def _to_domain(model: SearchProfileModel) -> SearchProfile:
    return SearchProfile(
        id=model.id,
        name=model.name,
        keywords=list(model.keywords or []),
        locations=list(model.locations or []),
        include_remote=model.include_remote,
        max_experience_level=(
            SeniorityLevel(model.max_experience_level) if model.max_experience_level else None
        ),
        excluded_keywords=list(model.excluded_keywords or []),
        enabled=model.enabled,
        source_config=dict(model.source_config or {}),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SearchProfileRepository:
    def create(self, db: Session, profile: SearchProfile) -> SearchProfile:
        model = SearchProfileModel(
            name=profile.name,
            keywords=list(profile.keywords),
            locations=list(profile.locations),
            include_remote=profile.include_remote,
            max_experience_level=(
                profile.max_experience_level.value if profile.max_experience_level else None
            ),
            excluded_keywords=list(profile.excluded_keywords),
            enabled=profile.enabled,
            source_config=dict(profile.source_config),
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def update(self, db: Session, profile_id: UUID, profile: SearchProfile) -> SearchProfile | None:
        model = db.get(SearchProfileModel, profile_id)
        if model is None:
            return None
        model.name = profile.name
        model.keywords = list(profile.keywords)
        model.locations = list(profile.locations)
        model.include_remote = profile.include_remote
        model.max_experience_level = (
            profile.max_experience_level.value if profile.max_experience_level else None
        )
        model.excluded_keywords = list(profile.excluded_keywords)
        model.enabled = profile.enabled
        model.source_config = dict(profile.source_config)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def delete(self, db: Session, profile_id: UUID) -> bool:
        model = db.get(SearchProfileModel, profile_id)
        if model is None:
            return False
        db.delete(model)
        db.commit()
        return True

    def get(self, db: Session, profile_id: UUID) -> SearchProfile | None:
        model = db.get(SearchProfileModel, profile_id)
        return _to_domain(model) if model else None

    def list_all(self, db: Session) -> list[SearchProfile]:
        models = (
            db.execute(select(SearchProfileModel).order_by(SearchProfileModel.created_at.asc()))
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def list_enabled(self, db: Session) -> list[SearchProfile]:
        models = (
            db.execute(select(SearchProfileModel).where(SearchProfileModel.enabled.is_(True)))
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
