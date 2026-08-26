"""FastAPI dependency providers.

Keeps route handlers free of construction logic - a route asks for a
service, not a database session plus three repositories.
"""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.providers.base import LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.db.session import SessionLocal
from app.repositories.analysis_repository import AnalysisRepository
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.candidate_service import CandidateService
from app.services.dashboard_service import DashboardService
from app.services.job_service import JobService


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_candidate_service() -> CandidateService:
    return CandidateService()


def get_job_service() -> JobService:
    return JobService()


def get_analysis_orchestrator(
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(llm_provider=llm_provider)


def get_analysis_repository() -> AnalysisRepository:
    return AnalysisRepository()


def get_dashboard_service() -> DashboardService:
    return DashboardService()
