"""Import all ORM models so Alembic autogenerate/metadata sees every table."""

from app.db.models.ai_trace import AITraceModel
from app.db.models.analysis import JobAnalysisModel
from app.db.models.app_settings import AppSettingsModel
from app.db.models.application_status import ApplicationStatusEventModel
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
from app.db.models.discovery import DiscoveredJobModel, DiscoveryRunModel, SearchProfileModel
from app.db.models.job import JobModel

__all__ = [
    "AITraceModel",
    "JobAnalysisModel",
    "AppSettingsModel",
    "ApplicationStatusEventModel",
    "AchievementModel",
    "CandidateModel",
    "CertificationModel",
    "EducationModel",
    "EvidenceModel",
    "ProjectModel",
    "SkillModel",
    "WorkExperienceModel",
    "DiscoveredJobModel",
    "DiscoveryRunModel",
    "SearchProfileModel",
    "JobModel",
]
