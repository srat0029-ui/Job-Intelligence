"""Unit tests for evidence-grounded company research: provenance, the
excerpt-grounding check that rejects unsupported claims, stale-source
freshness flagging, and research caching."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.company_research import LLMCompanyResearchOutput, LLMResearchClaimItem
from app.domain.enums import (
    AIOperationType,
    ClaimVerificationStatus,
    ResearchFetchStatus,
    ResearchSourceType,
)
from app.ingestion.research_provider import FixtureResearchProvider, RawResearchDocument
from app.repositories.research_repository import ResearchRepository
from app.services.company_research_service import CompanyResearchService, citable_claims

DOC_TEXT = (
    "Acme Corp builds real-time fraud detection software for banks. "
    "The engineering team recently launched a new machine learning pipeline "
    "for transaction scoring. Acme was founded in Melbourne in 2015."
)


def _provider(url: str = "https://acme.example/about", text: str = DOC_TEXT, published_at=None):
    provider = FixtureResearchProvider()
    provider.register(
        url,
        RawResearchDocument(
            url=url, domain="acme.example", title="About Acme", text=text,
            published_at=published_at, fetched_at=datetime.now(UTC),
        ),
    )
    return provider


def test_grounded_claim_is_stored_as_declared_verification_status(db):
    provider = _provider()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(
            claims=[
                LLMResearchClaimItem(
                    category="what_company_does",
                    claim="Acme builds fraud detection software for banks.",
                    supporting_excerpt=(
                        "Acme Corp builds real-time fraud detection software for banks."
                    ),
                    verification_status=ClaimVerificationStatus.VERIFIED_FACT,
                    confidence=0.95,
                )
            ]
        ),
    )
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())

    source = service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/about",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE,
    )
    assert source.fetch_status == ResearchFetchStatus.SUCCESS

    bundle = service.get_bundle(db, "Acme Corp")
    assert len(bundle.claims) == 1
    assert bundle.claims[0].verification_status == ClaimVerificationStatus.VERIFIED_FACT
    assert citable_claims(bundle.claims) == bundle.claims


def test_unsupported_claim_is_downgraded_to_unknown_and_excluded_from_citable(db):
    """The model asserts something the source text never said - this must
    never be treated as an established fact."""
    provider = _provider()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(
            claims=[
                LLMResearchClaimItem(
                    category="size",
                    claim="Acme has over 10,000 employees worldwide.",
                    supporting_excerpt="Acme has over 10,000 employees worldwide.",
                    verification_status=ClaimVerificationStatus.VERIFIED_FACT,
                    confidence=0.9,
                )
            ]
        ),
    )
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())

    service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/about",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE,
    )

    bundle = service.get_bundle(db, "Acme Corp")
    assert len(bundle.claims) == 1
    assert bundle.claims[0].verification_status == ClaimVerificationStatus.UNKNOWN
    assert bundle.claims[0].confidence == 0.0
    assert citable_claims(bundle.claims) == []


def test_stale_news_source_flags_recent_developments_claim_as_stale(db):
    old_date = datetime.now(UTC) - timedelta(days=400)
    provider = _provider(
        url="https://news.example/acme-launch",
        text="Acme just launched a new AI initiative for fraud scoring.",
        published_at=old_date,
    )
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(
            claims=[
                LLMResearchClaimItem(
                    category="ai_data_initiatives",
                    claim="Acme launched a new AI initiative for fraud scoring.",
                    supporting_excerpt="Acme just launched a new AI initiative for fraud scoring.",
                    verification_status=ClaimVerificationStatus.VERIFIED_FACT,
                    confidence=0.9,
                )
            ]
        ),
    )
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())
    service.add_source_and_research(
        db, company_name="Acme Corp", url="https://news.example/acme-launch",
        source_type=ResearchSourceType.NEWS,
    )

    bundle = service.get_bundle(db, "Acme Corp")
    assert len(bundle.claims) == 1
    assert bundle.claims[0].is_stale is True


def test_fresh_source_is_not_flagged_stale(db):
    recent_date = datetime.now(UTC) - timedelta(days=5)
    provider = _provider(
        url="https://news.example/acme-launch",
        text="Acme just launched a new AI initiative for fraud scoring.",
        published_at=recent_date,
    )
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(
            claims=[
                LLMResearchClaimItem(
                    category="ai_data_initiatives",
                    claim="Acme launched a new AI initiative for fraud scoring.",
                    supporting_excerpt="Acme just launched a new AI initiative for fraud scoring.",
                    verification_status=ClaimVerificationStatus.VERIFIED_FACT,
                    confidence=0.9,
                )
            ]
        ),
    )
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())
    service.add_source_and_research(
        db, company_name="Acme Corp", url="https://news.example/acme-launch",
        source_type=ResearchSourceType.NEWS,
    )

    bundle = service.get_bundle(db, "Acme Corp")
    assert bundle.claims[0].is_stale is False


def test_failed_fetch_is_recorded_without_raising(db):
    provider = FixtureResearchProvider()  # nothing registered -> LookupError
    fake_llm = FakeLLMProvider()
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())

    source = service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/missing",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE,
    )
    assert source.fetch_status == ResearchFetchStatus.FAILED
    assert source.error_message is not None

    bundle = service.get_bundle(db, "Acme Corp")
    assert bundle.claims == []


def test_research_is_cached_and_not_refetched_within_max_age(db):
    provider = _provider()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(claims=[]),
    )
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())

    first = service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/about",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE, max_age_days=30,
    )
    second = service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/about",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE, max_age_days=30,
    )
    assert first.id == second.id  # same cached row, no re-fetch/re-research

    sources = ResearchRepository().list_sources_for_company(db, "Acme Corp")
    assert len(sources) == 1


def test_force_refresh_bypasses_cache(db):
    provider = _provider()
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.COMPANY_RESEARCH_SYNTHESIS,
        LLMCompanyResearchOutput(claims=[]),
    )
    service = CompanyResearchService(fake_llm, provider, ResearchRepository())

    service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/about",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE,
    )
    service.add_source_and_research(
        db, company_name="Acme Corp", url="https://acme.example/about",
        source_type=ResearchSourceType.OFFICIAL_WEBSITE, force_refresh=True,
    )

    sources = ResearchRepository().list_sources_for_company(db, "Acme Corp")
    assert len(sources) == 2
