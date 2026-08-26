"""Domain model for the runtime-editable discovery/cost-control settings.

Kept separate from `app.core.config.Settings` (env-var based, requires a
restart to change) because these specifically need to be toggleable from
the Settings UI without redeploying - "ability to disable automatic AI
analysis" only means something if it's a live switch.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    auto_ai_analysis_enabled: bool = True
    max_ai_analyses_per_run: int = Field(default=20, ge=0)
    daily_ai_analysis_budget_usd: float | None = Field(default=None, ge=0)
