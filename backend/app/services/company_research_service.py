"""Evidence-grounded company/role research.

The anti-hallucination guarantee for company facts, mirroring
`app/services/matching_service.py`'s discipline for candidate evidence:

1. Research claims are extracted ONLY from a `ResearchSource`'s actual
   fetched text (see app/ingestion/research_provider.py) - the LLM is never
   asked to "tell me about this company" with no grounding text.
2. This code never trusts the model's `supporting_excerpt` on its word
   alone: `_excerpt_is_grounded` checks (after whitespace/case
   normalisation) that the excerpt is actually a substring of the source
   text the model was given. A claim that fails this check has its
   `verification_status` force-downgraded to UNKNOWN before being stored -
   kept for audit ("the model attempted this claim and it did not check
   out") but never treated as established fact. Every place a claim is
   handed to a downstream prompt as citable ("the ONLY company facts you
   may cite") filters UNKNOWN claims out first - see
   `citable_claims()` below.
3. Source quality (how trustworthy the origin is) and claim confidence
   (how clearly the text supports the claim) are stored and reasoned about
   separately - a HIGH-quality source can still yield a
   `reasonable_inference` claim.
4. Freshness is evaluated at READ time, not generation time
   (`_apply_freshness`): a claim in the "recent_developments" or
   "ai_data_initiatives" category sourced from a NEWS/PRESS_RELEASE page
   older than STALE_THRESHOLD_DAYS is flagged `is_stale=True` so callers
   (UI, application-strategy prompts) can visibly distinguish it rather
   than silently treating a five-year-old article as a current initiative.

Caching (Part 18): `add_source_and_research` skips re-fetching and
re-calling the LLM for a URL whose research is still fresh
(`max_age_days`), so the same company is not re-researched for every job
that happens to be at it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.ai.prompts import company_research_v1
from app.ai.providers.base import LLMProvider, LLMProviderError
from app.ai.schemas.company_research import LLMCompanyResearchOutput
from app.core.logging import get_logger
from app.domain.enums import (
    AIOperationType,
    ClaimVerificationStatus,
    ResearchFetchStatus,
    ResearchSourceType,
    SourceQualityTier,
)
from app.domain.research import CompanyResearchBundle, ResearchClaim, ResearchSource
from app.ingestion.research_provider import ResearchProvider, domain_of
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.research_repository import ResearchRepository

logger = get_logger(__name__)

SOURCE_TYPE_TO_QUALITY: dict[ResearchSourceType, SourceQualityTier] = {
    ResearchSourceType.OFFICIAL_WEBSITE: SourceQualityTier.HIGH,
    ResearchSourceType.CAREERS_PAGE: SourceQualityTier.HIGH,
    ResearchSourceType.ENGINEERING_BLOG: SourceQualityTier.HIGH,
    ResearchSourceType.PRESS_RELEASE: SourceQualityTier.HIGH,
    ResearchSourceType.NEWS: SourceQualityTier.MEDIUM,
    ResearchSourceType.COMPANY_DIRECTORY: SourceQualityTier.LOW,
    ResearchSourceType.OTHER: SourceQualityTier.MEDIUM,
}

STALE_THRESHOLD_DAYS = 365
STALE_SENSITIVE_CATEGORIES = {"recent_developments", "ai_data_initiatives"}
STALE_SOURCE_TYPES = {ResearchSourceType.NEWS, ResearchSourceType.PRESS_RELEASE}

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def _excerpt_is_grounded(excerpt: str, source_text: str) -> bool:
    normalized_excerpt = _normalize(excerpt)
    if not normalized_excerpt:
        return False
    return normalized_excerpt in _normalize(source_text)


class CompanyResearchService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        research_provider: ResearchProvider,
        research_repository: ResearchRepository | None = None,
        ai_trace_repository: AITraceRepository | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._research_provider = research_provider
        self._repository = research_repository or ResearchRepository()
        self._ai_trace_repository = ai_trace_repository or AITraceRepository()

    def get_bundle(self, db, company_name: str) -> CompanyResearchBundle:
        sources = self._repository.list_sources_for_company(db, company_name)
        claims = self._apply_freshness(
            self._repository.list_claims_for_company(db, company_name), sources
        )
        return CompanyResearchBundle(company_name=company_name, sources=sources, claims=claims)

    def add_source_and_research(
        self,
        db,
        *,
        company_name: str,
        url: str,
        source_type: ResearchSourceType,
        force_refresh: bool = False,
        max_age_days: int = 30,
    ) -> ResearchSource:
        if not force_refresh:
            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
            existing = [
                s
                for s in self._repository.list_recent_sources_for_company(
                    db, company_name, cutoff
                )
                if s.url == url
            ]
            if existing:
                logger.info("company_research_cache_hit", company=company_name, url=url)
                return existing[0]

        try:
            document = self._research_provider.fetch(url)
        except (LookupError, TimeoutError, ConnectionError, ValueError) as exc:
            logger.warning("company_research_fetch_failed", url=url, error=str(exc))
            return self._repository.save_source(
                db,
                ResearchSource(
                    company_name=company_name,
                    url=url,
                    domain=domain_of(url),
                    source_type=source_type,
                    source_quality=SOURCE_TYPE_TO_QUALITY[source_type],
                    fetch_status=ResearchFetchStatus.FAILED,
                    error_message=str(exc),
                    retrieved_at=datetime.now(UTC),
                ),
            )

        saved_source = self._repository.save_source(
            db,
            ResearchSource(
                company_name=company_name,
                url=document.url,
                domain=document.domain,
                title=document.title,
                source_type=source_type,
                source_quality=SOURCE_TYPE_TO_QUALITY[source_type],
                fetch_status=ResearchFetchStatus.SUCCESS,
                raw_text_excerpt=document.text,
                published_at=document.published_at,
                retrieved_at=document.fetched_at,
            ),
        )

        claims = self._extract_claims(
            db, company_name=company_name, source=saved_source, document_text=document.text
        )
        if claims:
            self._repository.save_claims(db, claims)
        return saved_source

    def _extract_claims(
        self, db, *, company_name: str, source: ResearchSource, document_text: str
    ) -> list[ResearchClaim]:
        assert source.id is not None
        try:
            result = self._llm_provider.generate_structured(
                operation_type=AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
                prompt_version=company_research_v1.PROMPT_VERSION,
                system_prompt=company_research_v1.SYSTEM_PROMPT,
                user_prompt=company_research_v1.build_user_prompt(
                    company_name=company_name, url=source.url, document_text=document_text
                ),
                output_schema=LLMCompanyResearchOutput,
                input_identifier=f"research:{company_name}:{source.id}",
            )
        except LLMProviderError as exc:
            self._ai_trace_repository.save(db, exc.trace)
            logger.error("company_research_synthesis_failed", url=source.url, error=str(exc))
            return []
        self._ai_trace_repository.save(db, result.trace)

        claims: list[ResearchClaim] = []
        for item in result.output.claims:
            grounded = _excerpt_is_grounded(item.supporting_excerpt, document_text)
            verification_status = item.verification_status
            if not grounded:
                logger.warning(
                    "company_research_claim_ungrounded",
                    url=source.url,
                    claim=item.claim[:200],
                )
                verification_status = ClaimVerificationStatus.UNKNOWN
            claims.append(
                ResearchClaim(
                    research_source_id=source.id,
                    company_name=company_name,
                    category=item.category,
                    claim=item.claim,
                    supporting_excerpt=item.supporting_excerpt,
                    verification_status=verification_status,
                    confidence=item.confidence if grounded else 0.0,
                )
            )
        return claims

    def _apply_freshness(
        self, claims: list[ResearchClaim], sources: list[ResearchSource]
    ) -> list[ResearchClaim]:
        sources_by_id = {s.id: s for s in sources if s.id is not None}
        now = datetime.now(UTC)
        result: list[ResearchClaim] = []
        for claim in claims:
            source = sources_by_id.get(claim.research_source_id)
            is_stale = False
            if (
                source is not None
                and source.source_type in STALE_SOURCE_TYPES
                and claim.category in STALE_SENSITIVE_CATEGORIES
                and source.published_at is not None
            ):
                published_at = source.published_at
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=UTC)
                age_days = (now - published_at).days
                is_stale = age_days > STALE_THRESHOLD_DAYS
            result.append(claim.model_copy(update={"is_stale": is_stale}))
        return result

def citable_claims(claims: list[ResearchClaim]) -> list[ResearchClaim]:
    """Claims safe to ever hand to a prompt as citable fact - excludes
    UNKNOWN (ungrounded-on-extraction) claims. Every service that builds a
    research-claims prompt block (strategy, CV tailoring, questions, cover
    letter) must filter through this first."""
    return [c for c in claims if c.verification_status != ClaimVerificationStatus.UNKNOWN]
