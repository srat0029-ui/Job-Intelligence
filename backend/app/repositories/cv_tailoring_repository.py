"""Data access for CV tailoring batches - versioned per workspace, same
regenerate-without-overwrite pattern as ApplicationStrategyRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.cv_tailoring import CVTailoringBatchModel
from app.domain.application_workspace import GenerationMeta
from app.domain.cv_tailoring import CVBulletSuggestion, CVTailoringBatch
from app.domain.enums import GenerationStatus


def _to_domain(model: CVTailoringBatchModel) -> CVTailoringBatch:
    return CVTailoringBatch(
        id=model.id,
        workspace_id=model.workspace_id,
        suggestions=[CVBulletSuggestion.model_validate(s) for s in (model.suggestions or [])],
        section_emphasis=list(model.section_emphasis or []),
        source_evidence_ids=list(model.source_evidence_ids or []),
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


class CVTailoringRepository:
    def save(self, db: Session, batch: CVTailoringBatch) -> CVTailoringBatch:
        latest = self._get_latest_model(db, batch.workspace_id)
        next_version = (latest.version + 1) if latest else 1
        if latest is not None:
            latest.status = GenerationStatus.ARCHIVED.value

        model = CVTailoringBatchModel(
            workspace_id=batch.workspace_id,
            suggestions=[s.model_dump(mode="json") for s in batch.suggestions],
            section_emphasis=batch.section_emphasis,
            source_evidence_ids=[str(i) for i in batch.source_evidence_ids],
            version=next_version,
            status=batch.meta.status,
            prompt_version=batch.meta.prompt_version,
            model=batch.meta.model,
            input_tokens=batch.meta.input_tokens,
            output_tokens=batch.meta.output_tokens,
            estimated_cost_usd=batch.meta.estimated_cost_usd,
            reviewer_result=batch.meta.reviewer_result,
            reviewer_issues=batch.meta.reviewer_issues,
            regeneration_attempt=batch.meta.regeneration_attempt,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def _get_latest_model(self, db: Session, workspace_id: UUID) -> CVTailoringBatchModel | None:
        return (
            db.execute(
                select(CVTailoringBatchModel)
                .where(CVTailoringBatchModel.workspace_id == workspace_id)
                .order_by(CVTailoringBatchModel.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def get_latest(self, db: Session, workspace_id: UUID) -> CVTailoringBatch | None:
        model = self._get_latest_model(db, workspace_id)
        return _to_domain(model) if model else None

    def list_history(self, db: Session, workspace_id: UUID) -> list[CVTailoringBatch]:
        models = (
            db.execute(
                select(CVTailoringBatchModel)
                .where(CVTailoringBatchModel.workspace_id == workspace_id)
                .order_by(CVTailoringBatchModel.version.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
