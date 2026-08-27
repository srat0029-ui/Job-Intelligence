"""Domain model for the runtime-editable discovery/cost-control settings.

Kept separate from `app.core.config.Settings` (env-var based, requires a
restart to change) because these specifically need to be toggleable from
the Settings UI without redeploying - "ability to disable automatic AI
analysis" only means something if it's a live switch. Scheduling fields
follow the same logic: enabling/disabling the scheduler or changing its
frequency shouldn't require a deploy.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    auto_ai_analysis_enabled: bool = True
    max_ai_analyses_per_run: int = Field(default=20, ge=0)
    daily_ai_analysis_budget_usd: float | None = Field(default=None, ge=0)

    auto_discovery_enabled: bool = False
    discovery_frequency_hours: int = Field(
        default=24, ge=1, le=168, description="How often the scheduler triggers a discovery run."
    )
    max_postings_per_source_per_run: int = Field(
        default=100,
        ge=1,
        description="Hard cap on postings fetched from any single source in one run.",
    )
    last_scheduled_run_at: datetime | None = None
    next_scheduled_run_at: datetime | None = None

    gmail_sync_frequency_minutes: int = Field(
        default=30,
        ge=5,
        description="How often the scheduler checks Gmail for new SEEK/LinkedIn alert emails.",
    )
    next_gmail_sync_at: datetime | None = None
