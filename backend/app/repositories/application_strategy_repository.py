"""Data access for ApplicationStrategy artefacts.

Regeneration never overwrites: `save()` always inserts a new row with
`version = previous latest + 1` and marks the previous latest row ARCHIVED -
prior versions stay fully readable via `list_history`.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.application_strategy import ApplicationStrategyModel
from app.domain.application_strategy import ApplicationStrategy, ConcernItem
from app.domain.application_workspace import GenerationMeta
from app.domain.enums import GenerationStatus


def _to_domain(model: ApplicationStrategyModel) -> ApplicationStrategy:
    return ApplicationStrategy(
        id=model.id,
        workspace_id=model.workspace_id,
        gap_analysis_id=model.gap_analysis_id,
        positioning=model.positioning,
        lead_evidence_ids=list(model.lead_evidence_ids or []),
        skills_to_emphasise=list(model.skills_to_emphasise or []),
        skills_to_deemphasise=list(model.skills_to_deemphasise or []),
        likely_concerns=[ConcernItem.model_validate(c) for c in (model.likely_concerns or [])],
        motivation_themes=list(model.motivation_themes or []),
        application_priority=model.application_priority,
        recommendation=model.recommendation,
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


class ApplicationStrategyRepository:
    def save(self, db: Session, strategy: ApplicationStrategy) -> ApplicationStrategy:
        latest = self._get_latest_model(db, strategy.workspace_id)
        next_version = (latest.version + 1) if latest else 1
        if latest is not None:
            latest.status = GenerationStatus.ARCHIVED.value

        model = ApplicationStrategyModel(
            workspace_id=strategy.workspace_id,
            gap_analysis_id=strategy.gap_analysis_id,
            positioning=strategy.positioning,
            lead_evidence_ids=[str(i) for i in strategy.lead_evidence_ids],
            skills_to_emphasise=strategy.skills_to_emphasise,
            skills_to_deemphasise=strategy.skills_to_deemphasise,
            likely_concerns=[c.model_dump(mode="json") for c in strategy.likely_concerns],
            motivation_themes=strategy.motivation_themes,
            application_priority=strategy.application_priority,
            recommendation=strategy.recommendation,
            source_evidence_ids=[str(i) for i in strategy.source_evidence_ids],
            source_research_claim_ids=[str(i) for i in strategy.source_research_claim_ids],
            version=next_version,
            status=strategy.meta.status,
            prompt_version=strategy.meta.prompt_version,
            model=strategy.meta.model,
            input_tokens=strategy.meta.input_tokens,
            output_tokens=strategy.meta.output_tokens,
            estimated_cost_usd=strategy.meta.estimated_cost_usd,
            reviewer_result=strategy.meta.reviewer_result,
            reviewer_issues=strategy.meta.reviewer_issues,
            regeneration_attempt=strategy.meta.regeneration_attempt,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def update_reviewer_result(
        self, db: Session, strategy_id: UUID, *, verdict: str, issues: list[str], status: str
    ) -> ApplicationStrategy | None:
        model = db.get(ApplicationStrategyModel, strategy_id)
        if model is None:
            return None
        model.reviewer_result = verdict
        model.reviewer_issues = issues
        model.status = status
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def _get_latest_model(
        self, db: Session, workspace_id: UUID
    ) -> ApplicationStrategyModel | None:
        return (
            db.execute(
                select(ApplicationStrategyModel)
                .where(ApplicationStrategyModel.workspace_id == workspace_id)
                .order_by(ApplicationStrategyModel.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def get_latest(self, db: Session, workspace_id: UUID) -> ApplicationStrategy | None:
        model = self._get_latest_model(db, workspace_id)
        return _to_domain(model) if model else None

    def get(self, db: Session, strategy_id: UUID) -> ApplicationStrategy | None:
        model = db.get(ApplicationStrategyModel, strategy_id)
        return _to_domain(model) if model else None

    def list_history(self, db: Session, workspace_id: UUID) -> list[ApplicationStrategy]:
        models = (
            db.execute(
                select(ApplicationStrategyModel)
                .where(ApplicationStrategyModel.workspace_id == workspace_id)
                .order_by(ApplicationStrategyModel.version.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
