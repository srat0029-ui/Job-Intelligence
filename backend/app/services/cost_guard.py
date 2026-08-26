"""Shared daily AI-budget check, reused by application-intelligence services.

Mirrors the same check `DiscoveryService._run_analysis_phase` already does
inline for the discovery auto-analysis phase - factored out here so
Milestone 4A's explicitly user-triggered generation calls respect the same
`AppSettings.daily_ai_analysis_budget_usd` limit without duplicating the
"sum today's AITrace cost" logic a second time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.app_settings_repository import AppSettingsRepository


class DailyBudgetExceededError(Exception):
    pass


def check_daily_budget_or_raise(
    db: Session,
    *,
    ai_trace_repository: AITraceRepository | None = None,
    app_settings_repository: AppSettingsRepository | None = None,
) -> None:
    settings = (app_settings_repository or AppSettingsRepository()).get(db)
    budget = settings.daily_ai_analysis_budget_usd
    if budget is None:
        return
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    spent_today = (ai_trace_repository or AITraceRepository()).sum_cost_since(db, today_start)
    if spent_today >= budget:
        raise DailyBudgetExceededError(
            f"Daily AI budget (${budget:.2f}) already reached (${spent_today:.2f} spent today) - "
            "increase the budget in Settings or wait until tomorrow to continue generating."
        )
