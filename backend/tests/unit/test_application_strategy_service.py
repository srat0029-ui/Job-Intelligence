"""Unit tests for ApplicationStrategy synthesis - structured output shape,
evidence/claim ID whitelisting, and that application_priority/recommendation
are copied through rather than recomputed."""

from __future__ import annotations

import uuid

from app.ai.providers.fake_provider import FakeLLMProvider
from app.ai.schemas.application_strategy import LLMApplicationStrategyOutput, LLMConcernItem
from app.domain.candidate import Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.enums import AIOperationType, ClaimVerificationStatus
from app.domain.job import ExtractedJob
from app.domain.research import ResearchClaim
from app.services.application_strategy_service import ApplicationStrategyService


def test_strategy_copies_priority_and_whitelists_ids():
    evidence = Evidence(
        id=uuid.uuid4(), source_type="project", source_label="Project X",
        statement="Built a data pipeline.", skill_tags=["python"],
    )
    claim = ResearchClaim(
        id=uuid.uuid4(), research_source_id=uuid.uuid4(), company_name="Acme",
        category="values", claim="Acme values learning.", supporting_excerpt="values learning",
        verification_status=ClaimVerificationStatus.VERIFIED_FACT, confidence=0.8,
    )
    fake_llm = FakeLLMProvider()
    fake_llm.set_response(
        AIOperationType.APPLICATION_STRATEGY,
        LLMApplicationStrategyOutput(
            positioning="Strong data engineering background.",
            lead_evidence_ids=[str(evidence.id), "bogus-id"],
            skills_to_emphasise=["Python"],
            skills_to_deemphasise=[],
            likely_concerns=[LLMConcernItem(concern="No AWS", response_strategy="Be honest.")],
            motivation_themes=["Learning culture"],
        ),
    )
    service = ApplicationStrategyService(fake_llm)

    strategy, trace = service.build(
        workspace_id=uuid.uuid4(),
        gap_analysis_id=uuid.uuid4(),
        extracted_job=ExtractedJob(title="Data Engineer", company="Acme"),
        evidence=[evidence],
        research_claims=[claim],
        gap_strategies=[],
        style=CommunicationStyle(),
        recommendation="apply",
        application_priority="strong_apply",
        input_identifier="test",
    )

    assert trace is not None
    assert strategy.recommendation == "apply"
    assert strategy.application_priority == "strong_apply"  # copied, never recomputed
    assert strategy.lead_evidence_ids == [evidence.id]  # bogus id stripped
    assert strategy.meta.status == "draft"
