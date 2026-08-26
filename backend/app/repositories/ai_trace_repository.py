"""Data access for the AI operation audit trail."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.ai_trace import AITraceModel
from app.domain.ai_trace import AITrace
from app.domain.enums import AIOperationType, AITraceStatus


def _to_domain(model: AITraceModel) -> AITrace:
    return AITrace(
        id=model.id,
        operation_type=AIOperationType(model.operation_type),
        prompt_version=model.prompt_version,
        model=model.model,
        input_identifier=model.input_identifier,
        status=AITraceStatus(model.status),
        latency_ms=model.latency_ms,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        estimated_cost_usd=model.estimated_cost_usd,
        error_message=model.error_message,
        attempt_number=model.attempt_number,
        created_at=model.created_at,
    )


class AITraceRepository:
    def save(self, db: Session, trace: AITrace) -> AITrace:
        model = AITraceModel(
            operation_type=trace.operation_type.value,
            prompt_version=trace.prompt_version,
            model=trace.model,
            input_identifier=trace.input_identifier,
            status=trace.status.value,
            latency_ms=trace.latency_ms,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            estimated_cost_usd=trace.estimated_cost_usd,
            error_message=trace.error_message,
            attempt_number=trace.attempt_number,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def list_for_input(self, db: Session, input_identifier: str) -> list[AITrace]:
        models = (
            db.execute(
                select(AITraceModel)
                .where(AITraceModel.input_identifier == input_identifier)
                .order_by(AITraceModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def list_for_input_prefix(self, db: Session, prefix: str) -> list[AITrace]:
        """All traces whose input_identifier starts with `prefix` - used by
        the Application Workspace debug/trace view, since one workspace's
        AI calls are tagged f"workspace:{id}:{step}" rather than one single
        identifier (see app/services/application_workflow_service.py)."""
        models = (
            db.execute(
                select(AITraceModel)
                .where(AITraceModel.input_identifier.like(f"{prefix}%"))
                .order_by(AITraceModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def list_recent(self, db: Session, limit: int = 100) -> list[AITrace]:
        models = (
            db.execute(select(AITraceModel).order_by(AITraceModel.created_at.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def sum_cost_since(self, db: Session, since: datetime) -> float:
        total = db.execute(
            select(func.coalesce(func.sum(AITraceModel.estimated_cost_usd), 0.0)).where(
                AITraceModel.created_at >= since
            )
        ).scalar_one()
        return float(total or 0.0)

    def sum_cost_for_input_identifiers(self, db: Session, input_identifiers: list[str]) -> float:
        if not input_identifiers:
            return 0.0
        total = db.execute(
            select(func.coalesce(func.sum(AITraceModel.estimated_cost_usd), 0.0)).where(
                AITraceModel.input_identifier.in_(input_identifiers)
            )
        ).scalar_one()
        return float(total or 0.0)

    def sum_cost_all_time(self, db: Session) -> float:
        total = db.execute(
            select(func.coalesce(func.sum(AITraceModel.estimated_cost_usd), 0.0))
        ).scalar_one()
        return float(total or 0.0)
