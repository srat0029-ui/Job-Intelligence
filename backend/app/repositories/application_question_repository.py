"""Data access for application-question responses.

Versioned per `question_key` (a normalised hash of question text) within a
workspace, so regenerating an answer to the same pasted question preserves
its own history without colliding with a different question asked in the
same workspace.
"""

from __future__ import annotations

import hashlib
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.application_question import ApplicationQuestionResponseModel
from app.domain.application_question import ApplicationQuestionResponse
from app.domain.application_workspace import GenerationMeta
from app.domain.enums import GenerationStatus, QuestionType

_WHITESPACE_RE = re.compile(r"\s+")


def compute_question_key(question_text: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", question_text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _to_domain(model: ApplicationQuestionResponseModel) -> ApplicationQuestionResponse:
    return ApplicationQuestionResponse(
        id=model.id,
        workspace_id=model.workspace_id,
        question_text=model.question_text,
        classifications=[QuestionType(c) for c in (model.classifications or [])],
        answered_deterministically=model.answered_deterministically,
        response_text=model.response_text,
        source_evidence_ids=list(model.source_evidence_ids or []),
        source_research_claim_ids=list(model.source_research_claim_ids or []),
        meta=GenerationMeta(
            version=model.version,
            status=model.status,
            prompt_version=model.prompt_version,
            model=model.model,
            generated_at=model.created_at,
            input_tokens=model.input_tokens,
            output_tokens=model.output_tokens,
            estimated_cost_usd=model.estimated_cost_usd,
            reviewer_result=model.reviewer_result,
            reviewer_issues=list(model.reviewer_issues or []),
            regeneration_attempt=model.regeneration_attempt,
        ),
        created_at=model.created_at,
    )


class ApplicationQuestionRepository:
    def save(
        self, db: Session, response: ApplicationQuestionResponse
    ) -> ApplicationQuestionResponse:
        question_key = compute_question_key(response.question_text)
        latest = self._get_latest_model(db, response.workspace_id, question_key)
        next_version = (latest.version + 1) if latest else 1
        if latest is not None:
            latest.status = GenerationStatus.ARCHIVED.value

        model = ApplicationQuestionResponseModel(
            workspace_id=response.workspace_id,
            question_key=question_key,
            question_text=response.question_text,
            classifications=[c.value for c in response.classifications],
            answered_deterministically=response.answered_deterministically,
            response_text=response.response_text,
            source_evidence_ids=[str(i) for i in response.source_evidence_ids],
            source_research_claim_ids=[str(i) for i in response.source_research_claim_ids],
            version=next_version,
            status=response.meta.status,
            prompt_version=response.meta.prompt_version,
            model=response.meta.model,
            input_tokens=response.meta.input_tokens,
            output_tokens=response.meta.output_tokens,
            estimated_cost_usd=response.meta.estimated_cost_usd,
            reviewer_result=response.meta.reviewer_result,
            reviewer_issues=response.meta.reviewer_issues,
            regeneration_attempt=response.meta.regeneration_attempt,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def _get_latest_model(
        self, db: Session, workspace_id: UUID, question_key: str
    ) -> ApplicationQuestionResponseModel | None:
        return (
            db.execute(
                select(ApplicationQuestionResponseModel)
                .where(
                    ApplicationQuestionResponseModel.workspace_id == workspace_id,
                    ApplicationQuestionResponseModel.question_key == question_key,
                )
                .order_by(ApplicationQuestionResponseModel.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def list_history(
        self, db: Session, workspace_id: UUID, question_text: str
    ) -> list[ApplicationQuestionResponse]:
        question_key = compute_question_key(question_text)
        models = (
            db.execute(
                select(ApplicationQuestionResponseModel)
                .where(
                    ApplicationQuestionResponseModel.workspace_id == workspace_id,
                    ApplicationQuestionResponseModel.question_key == question_key,
                )
                .order_by(ApplicationQuestionResponseModel.version.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def list_all_for_workspace(
        self, db: Session, workspace_id: UUID
    ) -> list[ApplicationQuestionResponse]:
        """Latest version of every distinct question asked in this
        workspace - used by the workspace Overview/Questions list."""
        models = (
            db.execute(
                select(ApplicationQuestionResponseModel)
                .where(ApplicationQuestionResponseModel.workspace_id == workspace_id)
                .order_by(ApplicationQuestionResponseModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        latest_by_key: dict[str, ApplicationQuestionResponseModel] = {}
        for m in models:
            if m.question_key not in latest_by_key:
                latest_by_key[m.question_key] = m
        return [_to_domain(m) for m in latest_by_key.values()]
