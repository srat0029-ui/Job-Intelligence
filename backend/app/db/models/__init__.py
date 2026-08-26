"""Import all ORM models so Alembic autogenerate/metadata sees every table."""

from app.db.models.ai_trace import AITraceModel
from app.db.models.analysis import JobAnalysisModel
from app.db.models.app_settings import AppSettingsModel
from app.db.models.application_status import ApplicationStatusEventModel
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
from app.db.models.company_watchlist import CompanyWatchlistModel
from app.db.models.discovery import (
    DiscoveredJobModel,
    DiscoveryRunModel,
    SearchProfileModel,
    SourceObservationModel,
)
from app.db.models.job import JobModel
from app.db.models.source_health import SourceHealthModel

__all__ = [
    "AITraceModel",
    "JobAnalysisModel",
    "AppSettingsModel",
    "ApplicationStatusEventModel",
    "AttentionItemModel",
    "AchievementModel",
    "CandidateModel",
    "CertificationModel",
    "EducationModel",
    "EvidenceModel",
    "ProjectModel",
    "SkillModel",
    "WorkExperienceModel",
    "CompanyWatchlistModel",
    "DiscoveredJobModel",
    "DiscoveryRunModel",
    "SearchProfileModel",
    "SourceObservationModel",
    "JobModel",
    "SourceHealthModel",
]
