"""Unit test for DashboardService.list_prioritized's sort/placement rules."""

from datetime import datetime
from uuid import uuid4

from app.domain.analysis import JobAnalysis
from app.domain.enums import Recommendation
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult
from app.domain.scoring import FitScore, ScoreComponent
from app.services.dashboard_service import DashboardService


def _component(score: float) -> ScoreComponent:
    return ScoreComponent(
        name="x", raw_score=score, weight=0.1, contributing_requirements=1, matched_requirements=1
    )


def _fit_score(overall: float) -> FitScore:
    return FitScore(
        overall_score=overall,
        recommendation=Recommendation.APPLY,
        technical_fit=_component(overall),
        project_relevance_fit=_component(overall),
        education_fit=_component(overall),
        experience_fit=_component(overall),
        domain_fit=_component(overall),
        location_fit=_component(overall),
        work_rights_fit=_component(overall),
        reasoning="test",
    )


class _FakeJob:
    def __init__(self, id_, title):
        self.id = id_
        self.title = title
        self.company = "Acme"
        self.location = None
        self.created_at = None


class _FakeJobRepository:
    def __init__(self, jobs):
        self._jobs = jobs

    def list_all(self, db):
        return self._jobs


class _FakeAnalysisRepository:
    def __init__(self, analyses):
        self._analyses = analyses

    def list_all(self, db):
        return self._analyses


def test_unanalyzed_jobs_sort_to_the_bottom():
    job_high = _FakeJob(uuid4(), "High Scorer")
    job_low = _FakeJob(uuid4(), "Low Scorer")
    job_unanalyzed = _FakeJob(uuid4(), "Never Analyzed")

    analyses = [
        JobAnalysis(
            job_id=job_high.id,
            extracted_job=ExtractedJob(title="t", company="c"),
            match_result=MatchResult(matches=[]),
            fit_score=_fit_score(90.0),
            created_at=datetime.now(),
        ),
        JobAnalysis(
            job_id=job_low.id,
            extracted_job=ExtractedJob(title="t", company="c"),
            match_result=MatchResult(matches=[]),
            fit_score=_fit_score(20.0),
            created_at=datetime.now(),
        ),
    ]

    service = DashboardService(
        job_repository=_FakeJobRepository([job_low, job_unanalyzed, job_high]),
        analysis_repository=_FakeAnalysisRepository(analyses),
    )

    items = service.list_prioritized(db=None)

    assert [i.title for i in items] == ["High Scorer", "Low Scorer", "Never Analyzed"]
    assert items[-1].latest_overall_score is None
