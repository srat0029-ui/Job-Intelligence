"""Unit tests for the bounded, ranked candidate-evidence retrieval used by
every application-intelligence prompt (relational, not vector-based - see
module docstring for why)."""

from __future__ import annotations

import uuid

from app.domain.candidate import Candidate, Evidence
from app.domain.enums import EvidenceTier, RequirementCategory, RequirementImportance
from app.domain.job import ExtractedJob, ExtractedRequirement
from app.domain.matching import MatchResult, RequirementMatch
from app.services.evidence_retrieval_service import evidence_by_id, rank_evidence_for_job


def _evidence(statement: str, skill_tags: list[str]) -> Evidence:
    return Evidence(
        id=uuid.uuid4(), source_type="project", source_label=statement[:20],
        statement=statement, skill_tags=skill_tags,
    )


def test_evidence_matching_job_requirements_ranks_above_irrelevant_evidence():
    relevant = _evidence(
        "Built a FastAPI backend with PostgreSQL.", ["python", "fastapi", "postgresql"]
    )
    irrelevant = _evidence("Organised a university sports club.", ["leadership", "events"])
    candidate = Candidate(name="Test", evidence=[irrelevant, relevant])
    job = ExtractedJob(
        title="Backend Engineer", company="Acme",
        requirements=[
            ExtractedRequirement(
                name="Python", raw_phrase="Python",
                category="technical_skill", importance="required",
            ),
            ExtractedRequirement(
                name="FastAPI", raw_phrase="FastAPI",
                category="technology", importance="preferred",
            ),
        ],
    )

    ranked = rank_evidence_for_job(candidate=candidate, extracted_job=job, max_evidence=10)
    assert ranked[0].id == relevant.id


def test_already_cited_evidence_is_boosted_to_the_top():
    e1 = _evidence("Statement one about databases.", ["sql"])
    e2 = _evidence("Statement two about unrelated topic.", ["public speaking"])
    candidate = Candidate(name="Test", evidence=[e1, e2])
    job = ExtractedJob(title="Data Engineer", company="Acme")
    match_result = MatchResult(
        matches=[
            RequirementMatch(
                requirement_name="SQL", category=RequirementCategory.TECHNICAL_SKILL,
                importance=RequirementImportance.REQUIRED, tier=EvidenceTier.EXPLICIT,
                confidence=0.9, evidence_ids=[e2.id], is_gap=False,
            )
        ]
    )

    ranked = rank_evidence_for_job(
        candidate=candidate, extracted_job=job, match_result=match_result, max_evidence=10
    )
    assert ranked[0].id == e2.id  # boosted despite no keyword overlap with the job


def test_result_is_bounded_by_max_evidence():
    candidate = Candidate(
        name="Test", evidence=[_evidence(f"Statement {i}", ["python"]) for i in range(20)]
    )
    job = ExtractedJob(title="Engineer", company="Acme")
    ranked = rank_evidence_for_job(candidate=candidate, extracted_job=job, max_evidence=5)
    assert len(ranked) == 5


def test_evidence_by_id_returns_only_requested_ids():
    e1 = _evidence("One", ["python"])
    e2 = _evidence("Two", ["java"])
    candidate = Candidate(name="Test", evidence=[e1, e2])
    result = evidence_by_id(candidate, [e1.id])
    assert [e.id for e in result] == [e1.id]
