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
from app.services.app_settings_service import AppSettingsService
from app.services.application_status_service import ApplicationStatusService
from app.services.candidate_service import CandidateService
from app.services.dashboard_service import DashboardService
from app.services.discovery_service import DiscoveryService
from app.services.job_service import JobService
from app.services.opportunity_service import OpportunityService
from app.services.search_profile_service import SearchProfileService


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


def get_search_profile_service() -> SearchProfileService:
    return SearchProfileService()


def get_app_settings_service() -> AppSettingsService:
    return AppSettingsService()


def get_application_status_service() -> ApplicationStatusService:
    return ApplicationStatusService()


def get_opportunity_service() -> OpportunityService:
    return OpportunityService()


def get_discovery_service(
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> DiscoveryService:
    return DiscoveryService(llm_provider=llm_provider)
