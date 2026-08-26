"""Structured output contract for job extraction.

Re-exports the domain ExtractedJob model rather than duplicating it: the
extraction LLM call's job is to *fill in* the domain's job schema, so there's
no separate "wire" shape to maintain. Kept as its own module so the AI layer
imports from `app.ai.schemas`, not directly from `app.domain`, keeping the
provider-facing contract explicit and easy to version independently later.
"""

from app.domain.job import ExtractedJob

__all__ = ["ExtractedJob"]
