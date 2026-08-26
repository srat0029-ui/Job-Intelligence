"""Data access for cover letters - versioned per workspace."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.cover_letter import CoverLetterModel
from app.domain.application_workspace import GenerationMeta
from app.domain.cover_letter import CoverLetter
from app.domain.enums import GenerationStatus


def _to_domain(model: CoverLetterModel) -> CoverLetter:
    return CoverLetter(
        id=model.id,
        workspace_id=model.workspace_id,
        body=model.body,
        source_evidence_ids=list(model.source_evidence_ids or []),
        source_research_claim_ids=list(model.source_research_claim_ids or []),
        meta=GenerationMeta(
            version=model.version,
            status=model.status,
            prompt_version=model.prompt_version,
            model=model.model,
            generated_at=model.created_at,
            input_tokens=model.input_tokens,
            output_tokens=model.output_tokens,
            estimated_cost_usd=model.estimated_cost_usd,
            reviewer_result=model.reviewer_result,
            reviewer_issues=list(model.reviewer_issues or []),
            regeneration_attempt=model.regeneration_attempt,
        ),
        created_at=model.created_at,
    )


class CoverLetterRepository:
    def save(self, db: Session, letter: CoverLetter) -> CoverLetter:
        latest = self._get_latest_model(db, letter.workspace_id)
        next_version = (latest.version + 1) if latest else 1
        if latest is not None:
            latest.status = GenerationStatus.ARCHIVED.value

        model = CoverLetterModel(
            workspace_id=letter.workspace_id,
            body=letter.body,
            source_evidence_ids=[str(i) for i in letter.source_evidence_ids],
            source_research_claim_ids=[str(i) for i in letter.source_research_claim_ids],
            version=next_version,
            status=letter.meta.status,
            prompt_version=letter.meta.prompt_version,
            model=letter.meta.model,
            input_tokens=letter.meta.input_tokens,
            output_tokens=letter.meta.output_tokens,
            estimated_cost_usd=letter.meta.estimated_cost_usd,
            reviewer_result=letter.meta.reviewer_result,
            reviewer_issues=letter.meta.reviewer_issues,
            regeneration_attempt=letter.meta.regeneration_attempt,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def _get_latest_model(self, db: Session, workspace_id: UUID) -> CoverLetterModel | None:
        return (
            db.execute(
                select(CoverLetterModel)
                .where(CoverLetterModel.workspace_id == workspace_id)
                .order_by(CoverLetterModel.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def get_latest(self, db: Session, workspace_id: UUID) -> CoverLetter | None:
        model = self._get_latest_model(db, workspace_id)
        return _to_domain(model) if model else None

    def list_history(self, db: Session, workspace_id: UUID) -> list[CoverLetter]:
        models = (
            db.execute(
                select(CoverLetterModel)
                .where(CoverLetterModel.workspace_id == workspace_id)
                .order_by(CoverLetterModel.version.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
