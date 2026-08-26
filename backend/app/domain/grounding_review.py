"""Domain model for the grounding-reviewer output.

The reviewer checks structured criteria (candidate grounding, company
grounding, job grounding, writing quality) rather than giving an open-ended
"looks good" - see app/services/grounding_reviewer_service.py. Code-level
structural checks (evidence/claim ID whitelist, invented metric/technology
detection) run before this and can force a FAIL outright regardless of what
the LLM reviewer itself concludes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import ReviewVerdict


class GroundingIssue(BaseModel):
    category: str  # e.g. "candidate_grounding", "company_grounding", "job_grounding", "writing"
    severity: str  # "warning" | "fail"
    description: str


class GroundingReviewResult(BaseModel):
    verdict: ReviewVerdict
    issues: list[GroundingIssue] = Field(default_factory=list)
