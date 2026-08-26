"""Data access for saved job analyses (extraction + matching + score)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.analysis import JobAnalysisModel
from app.domain.analysis import JobAnalysis
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult
from app.domain.scoring import FitScore


def _to_domain(model: JobAnalysisModel) -> JobAnalysis:
    return JobAnalysis(
        id=model.id,
        job_id=model.job_id,
        extracted_job=ExtractedJob.model_validate(model.extracted_job),
        match_result=MatchResult.model_validate(model.match_result),
        fit_score=FitScore.model_validate(model.fit_score),
        created_at=model.created_at,
    )


class AnalysisRepository:
    def save(
        self,
        db: Session,
        *,
        job_id: UUID,
        extracted_job: ExtractedJob,
        match_result: MatchResult,
        fit_score: FitScore,
    ) -> JobAnalysis:
        model = JobAnalysisModel(
            job_id=job_id,
            extracted_job=extracted_job.model_dump(mode="json"),
            match_result=match_result.model_dump(mode="json"),
            fit_score=fit_score.model_dump(mode="json"),
            overall_score=fit_score.overall_score,
            recommendation=fit_score.recommendation.value,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def get_latest_for_job(self, db: Session, job_id: UUID) -> JobAnalysis | None:
        model = (
            db.execute(
                select(JobAnalysisModel)
                .where(JobAnalysisModel.job_id == job_id)
                .order_by(JobAnalysisModel.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        return _to_domain(model) if model else None

    def list_all(self, db: Session) -> list[JobAnalysis]:
        models = (
            db.execute(select(JobAnalysisModel).order_by(JobAnalysisModel.created_at.desc()))
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
