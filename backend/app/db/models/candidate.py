"""ORM models for the candidate profile.

One candidate per instance for V1 (this is a personal tool), but modelled as
a full table (rather than a singleton config blob) so multi-candidate/
multi-tenant support is a additive change later, not a rewrite.
"""

import uuid
from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin

# Dimension for the future embedding column - matches common small
# embedding models (e.g. OpenAI text-embedding-3-small / Voyage lite).
# Unused by V1 deterministic matching; reserved for later semantic search
# over evidence statements once evidence volume makes it worthwhile.
EMBEDDING_DIM = 1536


class CandidateModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "candidates"

    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    preferred_job_categories: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    work_rights: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    salary_expectation_min: Mapped[int | None] = mapped_column(nullable=True)
    salary_expectation_max: Mapped[int | None] = mapped_column(nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), default="AUD")
    remote_preference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_technologies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    excluded_job_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    education: Mapped[list["EducationModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    work_history: Mapped[list["WorkExperienceModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    skills: Mapped[list["SkillModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    projects: Mapped[list["ProjectModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    achievements: Mapped[list["AchievementModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["CertificationModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["EvidenceModel"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class EducationModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "educations"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    institution: Mapped[str] = mapped_column(String(300))
    qualification: Mapped[str] = mapped_column(String(300))
    field_of_study: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="education")


class WorkExperienceModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "work_experiences"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    company: Mapped[str] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(300))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="work_history")


class SkillModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "skills"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    proficiency: Mapped[str | None] = mapped_column(String(50), nullable=True)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="skills")


class ProjectModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "projects"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    highlights: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="projects")


class AchievementModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "achievements"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="achievements")


class CertificationModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "certifications"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(300))
    issuer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="certifications")


class EvidenceModel(Base, UUIDPKMixin, TimestampMixin):
    """The atomic, citable unit of proof used by the matching engine.

    `embedding` is nullable and unused by V1 matching (which uses
    deterministic skill-tag lookups against a small, hand-curated evidence
    set) but is present so a future semantic retrieval pass over evidence
    statements doesn't require a schema migration - see docs/architecture.md.
    """

    __tablename__ = "evidence"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_label: Mapped[str] = mapped_column(String(300))
    statement: Mapped[str] = mapped_column(Text)
    skill_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="evidence")
