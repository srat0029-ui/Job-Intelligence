"""Unit tests for the shared daily AI-budget guard used by application-
intelligence generation endpoints."""

from __future__ import annotations

import pytest

from app.domain.ai_trace import AITrace
from app.domain.enums import AIOperationType, AITraceStatus
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.app_settings_repository import AppSettingsRepository
from app.services.cost_guard import DailyBudgetExceededError, check_daily_budget_or_raise


def test_no_budget_set_never_raises(db):
    check_daily_budget_or_raise(db)  # AppSettings default: daily_ai_analysis_budget_usd = None


def test_under_budget_does_not_raise(db):
    settings_repo = AppSettingsRepository()
    settings_repo.update(
        db, settings_repo.get(db).model_copy(update={"daily_ai_analysis_budget_usd": 10.0})
    )
    check_daily_budget_or_raise(db)


def test_budget_reached_raises(db):
    settings_repo = AppSettingsRepository()
    settings_repo.update(
        db, settings_repo.get(db).model_copy(update={"daily_ai_analysis_budget_usd": 0.01})
    )
    AITraceRepository().save(
        db,
        AITrace(
            operation_type=AIOperationType.APPLICATION_STRATEGY, prompt_version="v1", model="m",
            input_identifier="x", status=AITraceStatus.SUCCESS, latency_ms=1,
            estimated_cost_usd=0.02,
        ),
    )
    with pytest.raises(DailyBudgetExceededError):
        check_daily_budget_or_raise(db)
