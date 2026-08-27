"""Domain models for the deterministic fit score.

Scores are always computed in application code (see
app.services.scoring_service) from RequirementMatch tiers/confidences - never
by asking the LLM for a number. This module only models the *shape* of a
score so it can be persisted and displayed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import Recommendation


class ScoreComponent(BaseModel):
    """One weighted sub-score, kept transparent for later calibration."""

    name: str  # e.g. "technical_fit"
    raw_score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    contributing_requirements: int
    matched_requirements: int


class FitScore(BaseModel):
    overall_score: float = Field(ge=0.0, le=100.0)
    recommendation: Recommendation
    technical_fit: ScoreComponent
    project_relevance_fit: ScoreComponent
    education_fit: ScoreComponent
    experience_fit: ScoreComponent
    domain_fit: ScoreComponent
    location_fit: ScoreComponent
    work_rights_fit: ScoreComponent
    # Optional (not `| None` defaulting to a fallback ScoreComponent, unlike
    # the others) so job_analyses rows saved before this component existed
    # still round-trip through FitScore.model_validate without a migration -
    # None simply means "not computed for this analysis", same as any other
    # score component would mean before this field was added.
    career_stage_fit: ScoreComponent | None = None
    reasoning: str  # short, deterministic, user-facing explanation of *why*

    @property
    def components(self) -> list[ScoreComponent]:
        base = [
            self.technical_fit,
            self.project_relevance_fit,
            self.education_fit,
            self.experience_fit,
            self.domain_fit,
            self.location_fit,
            self.work_rights_fit,
        ]
        if self.career_stage_fit is not None:
            base.append(self.career_stage_fit)
        return base
