"""Structured output contract for the grounding-reviewer LLM check.

This supplements, never replaces, the code-level structural checks
(evidence/claim ID whitelisting, invented metric/technology detection) that
`GroundingReviewerService` runs first - a code-level FAIL always overrides
whatever this model call returns.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import ReviewVerdict


class LLMGroundingIssue(BaseModel):
    category: str = Field(
        description="One of: candidate_grounding, company_grounding, job_grounding, "
        "writing_quality."
    )
    severity: str = Field(description='"warning" or "fail".')
    description: str


class LLMGroundingReviewOutput(BaseModel):
    verdict: ReviewVerdict
    issues: list[LLMGroundingIssue] = Field(default_factory=list)
