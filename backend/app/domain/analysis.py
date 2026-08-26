"""Domain model tying extraction + matching + scoring into one saved result."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult
from app.domain.scoring import FitScore


class JobAnalysis(BaseModel):
    id: UUID | None = None
    job_id: UUID
    extracted_job: ExtractedJob
    match_result: MatchResult
    fit_score: FitScore
    created_at: datetime | None = None
