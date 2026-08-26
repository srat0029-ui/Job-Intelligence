"""Import all ORM models so Alembic autogenerate/metadata sees every table."""

from app.db.models.ai_trace import AITraceModel
from app.db.models.analysis import JobAnalysisModel
from app.db.models.candidate import (
    AchievementModel,
    CandidateModel,
    EducationModel,
    EvidenceModel,
    ProjectModel,
    SkillModel,
    WorkExperienceModel,
)
from app.db.models.job import JobModel

__all__ = [
    "AITraceModel",
    "JobAnalysisModel",
    "AchievementModel",
    "CandidateModel",
    "EducationModel",
    "EvidenceModel",
    "ProjectModel",
    "SkillModel",
    "WorkExperienceModel",
    "JobModel",
]
