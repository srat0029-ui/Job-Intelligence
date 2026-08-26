"""Builds the read-before-applying Application Brief.

Purely an assembly/formatting step over already-stored, already-grounded
records - no LLM call, no new claims. Every line traces back to either the
existing JobAnalysis (via `build_why_summary`, already used by the
opportunity feed) or the stored ApplicationStrategy's evidence/research
IDs.
"""

from __future__ import annotations

from app.domain.analysis import JobAnalysis
from app.domain.application_brief import ApplicationBrief, BriefEvidenceItem
from app.domain.application_strategy import ApplicationStrategy
from app.domain.candidate import Evidence
from app.domain.enums import EvidenceStrength
from app.domain.gap_analysis import GapAnalysis
from app.domain.research import ResearchClaim
from app.services.priority_service import build_why_summary


def build_brief(
    *,
    analysis: JobAnalysis,
    strategy: ApplicationStrategy,
    gap_analysis: GapAnalysis,
    evidence_by_id: dict[str, Evidence],
    research_claims: list[ResearchClaim],
) -> ApplicationBrief:
    why_fits = build_why_summary(analysis)

    best_evidence = [
        BriefEvidenceItem(evidence_id=str(eid), label=evidence_by_id[str(eid)].source_label)
        for eid in strategy.lead_evidence_ids
        if str(eid) in evidence_by_id
    ]

    key_gaps = [
        c.requirement_name for c in gap_analysis.coverage if c.strength == EvidenceStrength.GAP
    ]

    how_to_position = [strategy.positioning]
    if strategy.skills_to_emphasise:
        how_to_position.append(f"Emphasise: {', '.join(strategy.skills_to_emphasise)}")
    for gap in gap_analysis.gap_strategies:
        how_to_position.append(f"{gap.requirement_name}: {gap.guidance}")

    claims_by_id = {str(c.id): c for c in research_claims if c.id is not None}
    talking_points = [
        claims_by_id[str(cid)].claim
        for cid in strategy.source_research_claim_ids
        if str(cid) in claims_by_id
    ][:5]

    return ApplicationBrief(
        why_this_role_fits=why_fits,
        best_evidence_to_use=best_evidence,
        key_gaps=key_gaps,
        how_to_position=how_to_position,
        company_talking_points=talking_points,
        likely_application_themes=strategy.motivation_themes,
    )
