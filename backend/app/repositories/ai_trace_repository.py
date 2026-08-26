"""Data access for the AI operation audit trail."""

from __future__ import annotations

from sqlalchemy import select
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

    def list_recent(self, db: Session, limit: int = 100) -> list[AITrace]:
        models = (
            db.execute(select(AITraceModel).order_by(AITraceModel.created_at.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]
