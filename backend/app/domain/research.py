"""Domain models for evidence-grounded company/role research.

Mirrors the anti-hallucination discipline already established for candidate
evidence (see app/domain/candidate.py's Evidence + app/services/
matching_service.py): a `ResearchClaim` is never taken on the LLM's word
alone. Every claim must be produced from a stored `ResearchSource`'s actual
fetched text, and must carry a `supporting_excerpt` that
`app/services/company_research_service.py` verifies is actually present
(near-verbatim) in that source's text before the claim is persisted. A claim
that cannot be grounded this way is not stored as `verified_fact` or
`reasonable_inference` - it is dropped, never invented.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import (
    ClaimVerificationStatus,
    ResearchFetchStatus,
    ResearchSourceType,
    SourceQualityTier,
)


class ResearchSource(BaseModel):
    """One fetched document (a URL) used as the basis for company research.

    `raw_text_excerpt` is a bounded excerpt of the fetched page text (not
    necessarily the full page) - enough for claim grounding checks and for a
    human to verify provenance, without persisting an unbounded blob per
    fetch.
    """

    id: UUID | None = None
    company_name: str
    url: str
    domain: str
    title: str | None = None
    source_type: ResearchSourceType
    source_quality: SourceQualityTier
    fetch_status: ResearchFetchStatus
    raw_text_excerpt: str | None = None
    published_at: datetime | None = None  # when known (e.g. a news article's dateline)
    retrieved_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None


class ResearchClaim(BaseModel):
    """One factual statement about a company, grounded in one ResearchSource.

    `confidence` reflects how clearly the source text supports the claim -
    entirely separate from `ResearchSource.source_quality`, which reflects
    how trustworthy the source itself is. A high-quality source can still
    yield a low-confidence (inferred) claim, and vice versa.
    """

    id: UUID | None = None
    research_source_id: UUID
    company_name: str
    category: str  # free-form label, e.g. "products", "tech_focus", "values", "grad_program"
    claim: str
    supporting_excerpt: str
    verification_status: ClaimVerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    is_stale: bool = False  # set by freshness checks at read time, not generation time
    created_at: datetime | None = None


class CompanyResearchBundle(BaseModel):
    """Everything currently known about one company - the unit
    CompanyResearchService returns and caches against."""

    company_name: str
    sources: list[ResearchSource] = Field(default_factory=list)
    claims: list[ResearchClaim] = Field(default_factory=list)
