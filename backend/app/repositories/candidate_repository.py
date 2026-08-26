"""Data access for the candidate profile.

V1 is a single-user tool, so this repository models one candidate as a
singleton (`get_singleton`) rather than exposing arbitrary CRUD-by-id. Edits
to the profile are handled as a full replace of child collections
(education/work/skills/projects/achievements/evidence) - simple, correct,
and more than fast enough at this data volume. A future multi-candidate
version would add per-child diffing, but that's premature for one person's
own job search.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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
from app.domain.candidate import (
    Achievement,
    Candidate,
    CandidatePreferences,
    Certification,
    Education,
    Evidence,
    Project,
    Skill,
    WorkExperience,
)


def _load_query():
    return select(CandidateModel).options(
        selectinload(CandidateModel.education),
        selectinload(CandidateModel.work_history),
        selectinload(CandidateModel.skills),
        selectinload(CandidateModel.projects),
        selectinload(CandidateModel.achievements),
        selectinload(CandidateModel.certifications),
        selectinload(CandidateModel.evidence),
    )


def _to_domain(model: CandidateModel) -> Candidate:
    return Candidate(
        id=model.id,
        name=model.name,
        email=model.email,
        summary=model.summary,
        strengths=list(model.strengths or []),
        education=[
            Education(
                id=e.id,
                institution=e.institution,
                qualification=e.qualification,
                field_of_study=e.field_of_study,
                start_date=e.start_date,
                end_date=e.end_date,
                is_current=e.is_current,
                notes=e.notes,
            )
            for e in model.education
        ],
        work_history=[
            WorkExperience(
                id=w.id,
                company=w.company,
                title=w.title,
                start_date=w.start_date,
                end_date=w.end_date,
                is_current=w.is_current,
                summary=w.summary,
                technologies=list(w.technologies or []),
            )
            for w in model.work_history
        ],
        skills=[
            Skill(
                id=s.id,
                name=s.name,
                category=s.category,
                aliases=list(s.aliases or []),
                proficiency=s.proficiency,
            )
            for s in model.skills
        ],
        projects=[
            Project(
                id=p.id,
                name=p.name,
                description=p.description,
                technologies=list(p.technologies or []),
                github_url=p.github_url,
                highlights=list(p.highlights or []),
            )
            for p in model.projects
        ],
        achievements=[
            Achievement(id=a.id, title=a.title, description=a.description, date=a.date)
            for a in model.achievements
        ],
        certifications=[
            Certification(
                id=c.id,
                name=c.name,
                issuer=c.issuer,
                date=c.date,
                credential_url=c.credential_url,
            )
            for c in model.certifications
        ],
        evidence=[
            Evidence(
                id=ev.id,
                source_type=ev.source_type,
                source_id=ev.source_id,
                source_label=ev.source_label,
                statement=ev.statement,
                skill_tags=list(ev.skill_tags or []),
            )
            for ev in model.evidence
        ],
        preferences=CandidatePreferences(
            preferred_job_categories=list(model.preferred_job_categories or []),
            preferred_locations=list(model.preferred_locations or []),
            work_rights=list(model.work_rights or []),
            salary_expectation_min=model.salary_expectation_min,
            salary_expectation_max=model.salary_expectation_max,
            salary_currency=model.salary_currency,
            remote_preference=model.remote_preference,
            preferred_technologies=list(model.preferred_technologies or []),
            excluded_job_types=list(model.excluded_job_types or []),
        ),
    )


class CandidateRepository:
    def get_singleton(self, db: Session) -> Candidate | None:
        model = db.execute(_load_query().limit(1)).unique().scalar_one_or_none()
        return _to_domain(model) if model else None

    def get_singleton_model(self, db: Session) -> CandidateModel | None:
        return db.execute(_load_query().limit(1)).unique().scalar_one_or_none()

    def upsert(self, db: Session, candidate: Candidate) -> Candidate:
        model = self.get_singleton_model(db)
        if model is None:
            model = CandidateModel(name=candidate.name)
            db.add(model)

        model.name = candidate.name
        model.email = candidate.email
        model.summary = candidate.summary
        model.strengths = list(candidate.strengths)
        model.preferred_job_categories = list(candidate.preferences.preferred_job_categories)
        model.preferred_locations = list(candidate.preferences.preferred_locations)
        model.work_rights = list(candidate.preferences.work_rights)
        model.salary_expectation_min = candidate.preferences.salary_expectation_min
        model.salary_expectation_max = candidate.preferences.salary_expectation_max
        model.salary_currency = candidate.preferences.salary_currency
        model.remote_preference = candidate.preferences.remote_preference
        model.preferred_technologies = list(candidate.preferences.preferred_technologies)
        model.excluded_job_types = list(candidate.preferences.excluded_job_types)

        model.education = [
            EducationModel(
                institution=e.institution,
                qualification=e.qualification,
                field_of_study=e.field_of_study,
                start_date=e.start_date,
                end_date=e.end_date,
                is_current=e.is_current,
                notes=e.notes,
            )
            for e in candidate.education
        ]
        model.work_history = [
            WorkExperienceModel(
                company=w.company,
                title=w.title,
                start_date=w.start_date,
                end_date=w.end_date,
                is_current=w.is_current,
                summary=w.summary,
                technologies=list(w.technologies),
            )
            for w in candidate.work_history
        ]
        model.skills = [
            SkillModel(
                name=s.name,
                category=s.category,
                aliases=list(s.aliases),
                proficiency=s.proficiency,
            )
            for s in candidate.skills
        ]
        model.projects = [
            ProjectModel(
                name=p.name,
                description=p.description,
                technologies=list(p.technologies),
                github_url=p.github_url,
                highlights=list(p.highlights),
            )
            for p in candidate.projects
        ]
        model.achievements = [
            AchievementModel(title=a.title, description=a.description, date=a.date)
            for a in candidate.achievements
        ]
        model.certifications = [
            CertificationModel(
                name=c.name, issuer=c.issuer, date=c.date, credential_url=c.credential_url
            )
            for c in candidate.certifications
        ]
        model.evidence = [
            EvidenceModel(
                source_type=ev.source_type,
                source_id=ev.source_id,
                source_label=ev.source_label,
                statement=ev.statement,
                skill_tags=list(ev.skill_tags),
            )
            for ev in candidate.evidence
        ]

        db.commit()
        db.refresh(model)
        return _to_domain(model)
