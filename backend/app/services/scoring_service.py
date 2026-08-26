"""Deterministic fit-score calculation.

This is the one part of the spec that must NEVER ask an LLM for a number.
Every score here is a pure function of RequirementMatch tiers/importances
(classified by the LLM upstream) plus a couple of directly-computed
comparisons (location, work rights) that don't need any AI judgement at all.
Weights and thresholds are named constants so they're easy to find, discuss,
and eventually calibrate against real application outcomes (interview / no
interview) once that data exists.
"""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.domain.enums import (
    EvidenceSourceType,
    EvidenceTier,
    Recommendation,
    RequirementCategory,
    RequirementImportance,
)
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult, RequirementMatch
from app.domain.scoring import FitScore, ScoreComponent

# Points awarded per evidence tier. Confidence is stored for calibration but
# deliberately NOT multiplied into the score - blending a categorical
# classification with a continuous confidence would create false precision
# ("87.3% fit") the underlying classification can't actually support.
TIER_POINTS: dict[EvidenceTier, float] = {
    EvidenceTier.EXPLICIT: 100.0,
    EvidenceTier.TRANSFERABLE: 65.0,
    EvidenceTier.WEAK_INFERENCE: 35.0,
    EvidenceTier.NO_EVIDENCE: 0.0,
}

# A "required" requirement counts for more than a "preferred" one when
# averaging within a category.
IMPORTANCE_WEIGHT: dict[RequirementImportance, float] = {
    RequirementImportance.REQUIRED: 1.0,
    RequirementImportance.PREFERRED: 0.5,
}

# Overall-score weights, must sum to 1.0. Components with no contributing
# requirements are dropped and the remaining weights renormalised, rather
# than defaulted to a neutral score - a job posting that never mentions
# formal education shouldn't be treated as a below-average education fit.
COMPONENT_WEIGHTS: dict[str, float] = {
    "technical_fit": 0.30,
    "project_relevance_fit": 0.20,
    "experience_fit": 0.15,
    "domain_fit": 0.15,
    "education_fit": 0.10,
    "location_fit": 0.05,
    "work_rights_fit": 0.05,
}

TECHNICAL_CATEGORIES = {RequirementCategory.TECHNICAL_SKILL, RequirementCategory.TECHNOLOGY}
DOMAIN_CATEGORIES = {RequirementCategory.DOMAIN_KNOWLEDGE, RequirementCategory.SOFT_SKILL}

STRONG_APPLY_THRESHOLD = 80.0
APPLY_THRESHOLD = 65.0
STRETCH_THRESHOLD = 45.0


def _category_component(
    name: str, matches: list[RequirementMatch], weight: float
) -> ScoreComponent | None:
    if not matches:
        return None
    weighted_sum = 0.0
    weight_total = 0.0
    matched = 0
    for m in matches:
        w = IMPORTANCE_WEIGHT[m.importance]
        weighted_sum += TIER_POINTS[m.tier] * w
        weight_total += w
        if m.tier != EvidenceTier.NO_EVIDENCE:
            matched += 1
    raw = weighted_sum / weight_total if weight_total else 0.0
    return ScoreComponent(
        name=name,
        raw_score=round(raw, 1),
        weight=weight,
        contributing_requirements=len(matches),
        matched_requirements=matched,
    )


def _project_relevance_component(
    matches: list[RequirementMatch], candidate: Candidate, weight: float
) -> ScoreComponent | None:
    """How much of the match strength is backed by hands-on project evidence
    (vs. coursework, declared skills, or soft-skill claims alone)."""
    project_evidence_ids = {
        e.id
        for e in candidate.evidence
        if e.source_type == EvidenceSourceType.PROJECT.value and e.id
    }
    if not project_evidence_ids:
        return None
    project_backed = [
        m
        for m in matches
        if m.category in TECHNICAL_CATEGORIES | DOMAIN_CATEGORIES
        and any(eid in project_evidence_ids for eid in m.evidence_ids)
    ]
    return _category_component("project_relevance_fit", project_backed, weight)


def _location_component(
    extracted_job: ExtractedJob, candidate: Candidate, weight: float
) -> ScoreComponent:
    preferred = [loc.strip().lower() for loc in candidate.preferences.preferred_locations]
    job_location = (extracted_job.location or "").strip().lower()

    if not preferred or not job_location:
        raw = 70.0  # neutral - not enough information to penalise or reward
    elif any(p in job_location or job_location in p for p in preferred):
        raw = 100.0
    elif "remote" in job_location and candidate.preferences.remote_preference in (
        "remote",
        "hybrid",
    ):
        raw = 90.0
    else:
        raw = 30.0

    return ScoreComponent(
        name="location_fit",
        raw_score=raw,
        weight=weight,
        contributing_requirements=1,
        matched_requirements=1 if raw >= 70 else 0,
    )


def _work_rights_component(
    extracted_job: ExtractedJob, candidate: Candidate, weight: float
) -> ScoreComponent:
    work_rights_reqs = [
        r for r in extracted_job.requirements if r.category == RequirementCategory.WORK_RIGHTS
    ]
    candidate_rights = " ".join(candidate.preferences.work_rights).lower()

    if not work_rights_reqs:
        raw = 80.0  # neutral-positive - most postings that require sponsorship say so explicitly
        matched = 1
    else:
        satisfied = sum(
            1
            for r in work_rights_reqs
            if any(token in candidate_rights for token in r.name.lower().split())
        )
        raw = 100.0 * satisfied / len(work_rights_reqs) if work_rights_reqs else 80.0
        matched = satisfied

    return ScoreComponent(
        name="work_rights_fit",
        raw_score=round(raw, 1),
        weight=weight,
        contributing_requirements=max(len(work_rights_reqs), 1),
        matched_requirements=matched,
    )


def _recommendation(overall: float, matches: list[RequirementMatch]) -> Recommendation:
    hard_gaps = [
        m
        for m in matches
        if m.importance == RequirementImportance.REQUIRED and m.tier == EvidenceTier.NO_EVIDENCE
    ]
    if hard_gaps and overall < STRONG_APPLY_THRESHOLD:
        # A missing must-have caps the recommendation even if other areas
        # score well - deterministic rule, not an LLM judgement call.
        if overall >= STRETCH_THRESHOLD:
            return Recommendation.STRETCH
        return Recommendation.LOW_PRIORITY
    if overall >= STRONG_APPLY_THRESHOLD:
        return Recommendation.STRONG_APPLY
    if overall >= APPLY_THRESHOLD:
        return Recommendation.APPLY
    if overall >= STRETCH_THRESHOLD:
        return Recommendation.STRETCH
    return Recommendation.LOW_PRIORITY


def _reasoning(
    overall: float, recommendation: Recommendation, matches: list[RequirementMatch]
) -> str:
    gaps = [m.requirement_name for m in matches if m.is_gap][:3]
    strengths = [
        m.requirement_name
        for m in matches
        if m.tier == EvidenceTier.EXPLICIT and not m.is_gap
    ][:3]
    parts = [f"Overall fit {overall:.0f}/100 -> {recommendation.value.replace('_', ' ').title()}."]
    if strengths:
        parts.append(f"Strong match on {', '.join(strengths)}.")
    if gaps:
        parts.append(f"Notable gaps: {', '.join(gaps)}.")
    return " ".join(parts)


class ScoringService:
    """Computes an explainable FitScore from a MatchResult. Pure/deterministic
    given its inputs - no I/O, no LLM calls - which is what makes it easy to
    unit test and safe to re-run for score stability checks in the eval
    framework."""

    def score(
        self, *, extracted_job: ExtractedJob, match_result: MatchResult, candidate: Candidate
    ) -> FitScore:
        matches = match_result.matches
        technical_matches = [m for m in matches if m.category in TECHNICAL_CATEGORIES]
        domain_matches = [m for m in matches if m.category in DOMAIN_CATEGORIES]
        education_matches = [m for m in matches if m.category == RequirementCategory.EDUCATION]
        experience_matches = [m for m in matches if m.category == RequirementCategory.EXPERIENCE]

        components: dict[str, ScoreComponent | None] = {
            "technical_fit": _category_component(
                "technical_fit", technical_matches, COMPONENT_WEIGHTS["technical_fit"]
            ),
            "project_relevance_fit": _project_relevance_component(
                matches, candidate, COMPONENT_WEIGHTS["project_relevance_fit"]
            ),
            "experience_fit": _category_component(
                "experience_fit", experience_matches, COMPONENT_WEIGHTS["experience_fit"]
            ),
            "domain_fit": _category_component(
                "domain_fit", domain_matches, COMPONENT_WEIGHTS["domain_fit"]
            ),
            "education_fit": _category_component(
                "education_fit", education_matches, COMPONENT_WEIGHTS["education_fit"]
            ),
            "location_fit": _location_component(
                extracted_job, candidate, COMPONENT_WEIGHTS["location_fit"]
            ),
            "work_rights_fit": _work_rights_component(
                extracted_job, candidate, COMPONENT_WEIGHTS["work_rights_fit"]
            ),
        }

        available = {k: v for k, v in components.items() if v is not None}
        weight_total = sum(c.weight for c in available.values()) or 1.0
        overall = sum(c.raw_score * c.weight for c in available.values()) / weight_total
        overall = round(overall, 1)

        def _fallback(name: str) -> ScoreComponent:
            return ScoreComponent(
                name=name,
                raw_score=70.0,
                weight=COMPONENT_WEIGHTS[name],
                contributing_requirements=0,
                matched_requirements=0,
            )

        recommendation = _recommendation(overall, matches)
        reasoning = _reasoning(overall, recommendation, matches)

        return FitScore(
            overall_score=overall,
            recommendation=recommendation,
            technical_fit=components["technical_fit"] or _fallback("technical_fit"),
            project_relevance_fit=(
                components["project_relevance_fit"] or _fallback("project_relevance_fit")
            ),
            education_fit=components["education_fit"] or _fallback("education_fit"),
            experience_fit=components["experience_fit"] or _fallback("experience_fit"),
            domain_fit=components["domain_fit"] or _fallback("domain_fit"),
            location_fit=components["location_fit"],  # type: ignore[arg-type]
            work_rights_fit=components["work_rights_fit"],  # type: ignore[arg-type]
            reasoning=reasoning,
        )
