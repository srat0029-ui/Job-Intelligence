"""Import all ORM models so Alembic autogenerate/metadata sees every table."""

from app.db.models.ai_trace import AITraceModel
from app.db.models.analysis import JobAnalysisModel
from app.db.models.app_settings import AppSettingsModel
from app.db.models.application_question import ApplicationQuestionResponseModel
from app.db.models.application_status import ApplicationStatusEventModel
from app.db.models.application_strategy import ApplicationStrategyModel
from app.db.models.application_workspace import ApplicationWorkspaceModel
from app.db.models.attention import AttentionItemModel
from app.db.models.candidate import (
    AchievementModel,
    CandidateModel,
    CertificationModel,
    EducationModel,
    EvidenceModel,
    ProjectModel,
    SkillModel,
    WorkExperienceModel,
)
from app.db.models.communication_style import CommunicationStyleModel
from app.db.models.company_watchlist import CompanyWatchlistModel
from app.db.models.cover_letter import CoverLetterModel
from app.db.models.cv_tailoring import CVTailoringBatchModel
from app.db.models.discovery import (
    DiscoveredJobModel,
    DiscoveryRunModel,
    SearchProfileModel,
    SourceObservationModel,
)
from app.db.models.gap_analysis import GapAnalysisModel
from app.db.models.job import JobModel
from app.db.models.research import ResearchClaimModel, ResearchSourceModel
from app.db.models.source_health import SourceHealthModel

__all__ = [
    "AITraceModel",
    "JobAnalysisModel",
    "AppSettingsModel",
    "ApplicationQuestionResponseModel",
    "ApplicationStatusEventModel",
    "ApplicationStrategyModel",
    "ApplicationWorkspaceModel",
    "AttentionItemModel",
    "AchievementModel",
    "CandidateModel",
    "CertificationModel",
    "EducationModel",
    "EvidenceModel",
    "ProjectModel",
    "SkillModel",
    "WorkExperienceModel",
    "CommunicationStyleModel",
    "CompanyWatchlistModel",
    "CoverLetterModel",
    "CVTailoringBatchModel",
    "DiscoveredJobModel",
    "DiscoveryRunModel",
    "SearchProfileModel",
    "SourceObservationModel",
    "GapAnalysisModel",
    "JobModel",
    "ResearchClaimModel",
    "ResearchSourceModel",
    "SourceHealthModel",
]
