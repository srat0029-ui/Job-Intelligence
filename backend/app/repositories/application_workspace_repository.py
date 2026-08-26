"""Data access for the Application Workspace."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.application_workspace import ApplicationWorkspaceModel
from app.domain.application_workspace import ApplicationWorkspace


def _to_domain(model: ApplicationWorkspaceModel) -> ApplicationWorkspace:
    return ApplicationWorkspace(
        id=model.id,
        job_id=model.job_id,
        notes=model.notes,
        research_company_name=model.research_company_name,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class ApplicationWorkspaceRepository:
    def get_by_job_id(self, db: Session, job_id: UUID) -> ApplicationWorkspace | None:
        model = db.execute(
            select(ApplicationWorkspaceModel).where(ApplicationWorkspaceModel.job_id == job_id)
        ).scalar_one_or_none()
        return _to_domain(model) if model else None

    def get(self, db: Session, workspace_id: UUID) -> ApplicationWorkspace | None:
        model = db.get(ApplicationWorkspaceModel, workspace_id)
        return _to_domain(model) if model else None

    def get_or_create(self, db: Session, job_id: UUID) -> ApplicationWorkspace:
        model = db.execute(
            select(ApplicationWorkspaceModel).where(ApplicationWorkspaceModel.job_id == job_id)
        ).scalar_one_or_none()
        if model is None:
            model = ApplicationWorkspaceModel(job_id=job_id)
            db.add(model)
            try:
                db.commit()
            except IntegrityError:
                # Lost a race against a concurrent get_or_create for the
                # same job (e.g. a double-fired effect on the client) - the
                # other insert already won, so just read what it created.
                db.rollback()
                model = db.execute(
                    select(ApplicationWorkspaceModel).where(
                        ApplicationWorkspaceModel.job_id == job_id
                    )
                ).scalar_one()
            else:
                db.refresh(model)
        return _to_domain(model)

    def update_notes(
        self, db: Session, workspace_id: UUID, notes: str
    ) -> ApplicationWorkspace | None:
        model = db.get(ApplicationWorkspaceModel, workspace_id)
        if model is None:
            return None
        model.notes = notes
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def set_research_company_name(
        self, db: Session, workspace_id: UUID, company_name: str
    ) -> ApplicationWorkspace | None:
        model = db.get(ApplicationWorkspaceModel, workspace_id)
        if model is None:
            return None
        model.research_company_name = company_name
        db.commit()
        db.refresh(model)
        return _to_domain(model)
