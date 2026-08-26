"""Data access for gap analyses."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.gap_analysis import GapAnalysisModel
from app.domain.gap_analysis import GapAnalysis, GapStrategyItem, RequirementCoverage


def _to_domain(model: GapAnalysisModel) -> GapAnalysis:
    return GapAnalysis(
        id=model.id,
        workspace_id=model.workspace_id,
        job_analysis_id=model.job_analysis_id,
        coverage=[RequirementCoverage.model_validate(c) for c in model.coverage],
        gap_strategies=[GapStrategyItem.model_validate(g) for g in model.gap_strategies],
        prompt_version=model.prompt_version,
        model=model.model,
        generated_at=model.created_at,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        estimated_cost_usd=model.estimated_cost_usd,
    )


class GapAnalysisRepository:
    def save(self, db: Session, analysis: GapAnalysis) -> GapAnalysis:
        model = GapAnalysisModel(
            workspace_id=analysis.workspace_id,
            job_analysis_id=analysis.job_analysis_id,
            coverage=[c.model_dump(mode="json") for c in analysis.coverage],
            gap_strategies=[g.model_dump(mode="json") for g in analysis.gap_strategies],
            prompt_version=analysis.prompt_version,
            model=analysis.model,
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
            estimated_cost_usd=analysis.estimated_cost_usd,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def get_latest_for_workspace(self, db: Session, workspace_id: UUID) -> GapAnalysis | None:
        model = (
            db.execute(
                select(GapAnalysisModel)
                .where(GapAnalysisModel.workspace_id == workspace_id)
                .order_by(GapAnalysisModel.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        return _to_domain(model) if model else None

    def get(self, db: Session, gap_analysis_id: UUID) -> GapAnalysis | None:
        model = db.get(GapAnalysisModel, gap_analysis_id)
        return _to_domain(model) if model else None
