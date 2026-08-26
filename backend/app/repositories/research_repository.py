"""Data access for company/role research sources and claims."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.research import ResearchClaimModel, ResearchSourceModel
from app.domain.enums import (
    ClaimVerificationStatus,
    ResearchFetchStatus,
    ResearchSourceType,
    SourceQualityTier,
)
from app.domain.research import ResearchClaim, ResearchSource


def _source_to_domain(model: ResearchSourceModel) -> ResearchSource:
    return ResearchSource(
        id=model.id,
        company_name=model.company_name,
        url=model.url,
        domain=model.domain,
        title=model.title,
        source_type=ResearchSourceType(model.source_type),
        source_quality=SourceQualityTier(model.source_quality),
        fetch_status=ResearchFetchStatus(model.fetch_status),
        raw_text_excerpt=model.raw_text_excerpt,
        published_at=model.published_at,
        retrieved_at=model.retrieved_at,
        error_message=model.error_message,
        created_at=model.created_at,
    )


def _claim_to_domain(model: ResearchClaimModel) -> ResearchClaim:
    return ResearchClaim(
        id=model.id,
        research_source_id=model.research_source_id,
        company_name=model.company_name,
        category=model.category,
        claim=model.claim,
        supporting_excerpt=model.supporting_excerpt,
        verification_status=ClaimVerificationStatus(model.verification_status),
        confidence=model.confidence,
        created_at=model.created_at,
    )


class ResearchRepository:
    def save_source(self, db: Session, source: ResearchSource) -> ResearchSource:
        model = ResearchSourceModel(
            company_name=source.company_name,
            url=source.url,
            domain=source.domain,
            title=source.title,
            source_type=source.source_type.value,
            source_quality=source.source_quality.value,
            fetch_status=source.fetch_status.value,
            raw_text_excerpt=source.raw_text_excerpt,
            published_at=source.published_at,
            retrieved_at=source.retrieved_at,
            error_message=source.error_message,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _source_to_domain(model)

    def save_claims(self, db: Session, claims: list[ResearchClaim]) -> list[ResearchClaim]:
        models = [
            ResearchClaimModel(
                research_source_id=c.research_source_id,
                company_name=c.company_name,
                category=c.category,
                claim=c.claim,
                supporting_excerpt=c.supporting_excerpt,
                verification_status=c.verification_status.value,
                confidence=c.confidence,
            )
            for c in claims
        ]
        db.add_all(models)
        db.commit()
        for m in models:
            db.refresh(m)
        return [_claim_to_domain(m) for m in models]

    def list_sources_for_company(self, db: Session, company_name: str) -> list[ResearchSource]:
        models = (
            db.execute(
                select(ResearchSourceModel)
                .where(ResearchSourceModel.company_name == company_name)
                .order_by(ResearchSourceModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_source_to_domain(m) for m in models]

    def list_recent_sources_for_company(
        self, db: Session, company_name: str, since: datetime
    ) -> list[ResearchSource]:
        models = (
            db.execute(
                select(ResearchSourceModel).where(
                    ResearchSourceModel.company_name == company_name,
                    ResearchSourceModel.fetch_status == ResearchFetchStatus.SUCCESS.value,
                    ResearchSourceModel.created_at >= since,
                )
            )
            .scalars()
            .all()
        )
        return [_source_to_domain(m) for m in models]

    def list_claims_for_company(self, db: Session, company_name: str) -> list[ResearchClaim]:
        models = (
            db.execute(
                select(ResearchClaimModel)
                .where(ResearchClaimModel.company_name == company_name)
                .order_by(ResearchClaimModel.confidence.desc())
            )
            .scalars()
            .all()
        )
        return [_claim_to_domain(m) for m in models]

    def get_claims_by_ids(self, db: Session, claim_ids: list[UUID]) -> list[ResearchClaim]:
        if not claim_ids:
            return []
        models = (
            db.execute(select(ResearchClaimModel).where(ResearchClaimModel.id.in_(claim_ids)))
            .scalars()
            .all()
        )
        return [_claim_to_domain(m) for m in models]
