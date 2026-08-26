"""Structured output contract for company-research claim extraction.

The model may only extract claims from the ONE document's text it was
given in the prompt - `supporting_excerpt` must be a (near-)verbatim
fragment of that text. `CompanyResearchService` verifies this in code
before persisting a claim (see its module docstring); a claim whose excerpt
cannot be located in the source text is dropped, never trusted on the
model's word alone - the same discipline as evidence-id whitelisting in
`app/services/matching_service.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import ClaimVerificationStatus


class LLMResearchClaimItem(BaseModel):
    category: str = Field(
        description="One of: what_company_does, products_services, industry, size, "
        "recent_developments, tech_focus, ai_data_initiatives, values, "
        "early_career_program, role_team_context, other."
    )
    claim: str = Field(description="One concise, user-facing factual statement.")
    supporting_excerpt: str = Field(
        description="A short fragment COPIED from the provided document text that "
        "directly supports this claim. Never paraphrase this field."
    )
    verification_status: ClaimVerificationStatus = Field(
        description="verified_fact if the excerpt directly states this; "
        "reasonable_inference if it's a plausible but non-explicit reading of the excerpt."
    )
    confidence: float = Field(ge=0.0, le=1.0)


class LLMCompanyResearchOutput(BaseModel):
    claims: list[LLMResearchClaimItem] = Field(default_factory=list)
