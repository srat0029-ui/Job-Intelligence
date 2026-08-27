"""Deterministic fit-score calculation.

This is the one part of the spec that must NEVER ask an LLM for a number.
Every score here is a pure function of RequirementMatch tiers/importances
(classified by the LLM upstream) plus a couple of directly-computed
comparisons (location, work rights, career stage) that don't need any AI
judgement at all. Weights and thresholds are named constants so they're easy
to find, discuss, and eventually calibrate against real application outcomes
(interview / no interview) once that data exists.

Recommendation-quality review (see the calibration notes in
tests/unit/test_scoring_service.py) found two structural problems with the
original version of this module, both fixed here:

1. Score saturation at a single value. When extraction found ZERO
   requirements for a job (see job_page_enrichment.py's login-wall fix -
   the actual root cause for most real postings), every LLM-matched
   category (technical/project/experience/domain/education) dropped out of
   the weighted average entirely, leaving only the two always-present
   deterministic components (location_fit, work_rights_fit) - which for a
   geographically-matched posting with no explicit work-rights requirement
   converge on almost exactly the same number every time (90.0: (100*.05 +
   80*.05) / 0.10). `_score_caps`'s "no extractable requirements" cap fixes
   this directly: a job we genuinely know almost nothing about gets capped
   at STRETCH-tier confidence, never STRONG_APPLY, rather than defaulting
   to a big confident-looking number.
2. No first-class career-stage signal. A technically-relevant but clearly
   senior/architect-level posting (e.g. "AI/ML Security Architect") had
   nothing in this module distinguishing it from a genuine graduate role
   with the same skill overlap - `career_stage_fit` (using the extraction
   step's own `seniority` classification against the candidate's
   self-declared target level, never a hardcoded assumption) and the
   seniority-gap caps in `_score_caps` fix that.
"""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.domain.enums import (
    EvidenceSourceType,
    EvidenceTier,
    Recommendation,
    RequirementCategory,
    RequirementImportance,
    SeniorityLevel,
)
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult, RequirementMatch
from app.domain.scoring import FitScore, ScoreComponent
from app.services.prefilter_service import SENIORITY_RANK

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
# `career_stage_fit` carved its 0.15 mainly out of technical_fit/
# project_relevance_fit/experience_fit - skill overlap alone was
# overweighted relative to "is this realistically the right level for me",
# which is exactly the AI/ML Security Architect-style failure mode the
# recommendation-quality review called out.
COMPONENT_WEIGHTS: dict[str, float] = {
    "technical_fit": 0.25,
    "project_relevance_fit": 0.15,
    "career_stage_fit": 0.15,
    "experience_fit": 0.10,
    "domain_fit": 0.15,
    "education_fit": 0.10,
    "location_fit": 0.05,
    "work_rights_fit": 0.05,
}

TECHNICAL_CATEGORIES = {RequirementCategory.TECHNICAL_SKILL, RequirementCategory.TECHNOLOGY}
DOMAIN_CATEGORIES = {RequirementCategory.DOMAIN_KNOWLEDGE, RequirementCategory.SOFT_SKILL}
CORE_CATEGORIES = TECHNICAL_CATEGORIES | DOMAIN_CATEGORIES

STRONG_APPLY_THRESHOLD = 80.0
APPLY_THRESHOLD = 65.0
STRETCH_THRESHOLD = 45.0

# --- deterministic score caps (Section 5 of the recommendation-quality
# review) - each fires independently on a named, principled condition; the
# final score is the min of the raw weighted average and every cap that
# fired, so multiple genuine concerns compound rather than hide each other.
ZERO_EVIDENCE_SCORE_CAP = 50.0
LEAD_LEVEL_SCORE_CAP = 35.0
SENIOR_LEVEL_SCORE_CAP = 60.0
HARD_GAP_SCORE_CAP = 75.0
TRANSFERABLE_MAJORITY_SCORE_CAP = 78.0
MIN_CORE_REQUIREMENTS_FOR_TRANSFERABLE_CAP = 2

# Words found in the candidate's own stored preferred-job-category strings
# imply their target seniority ceiling - a generic, profile-driven default
# (never a hardcoded assumption about any one candidate) that falls back to
# JUNIOR (a graduate who's also open to junior roles) when nothing in the
# stored preferences implies a level at all.
_SENIORITY_WORDS_BY_LEVEL: list[tuple[str, SeniorityLevel]] = [
    ("intern", SeniorityLevel.INTERN),
    ("entry level", SeniorityLevel.GRADUATE),
    ("entry-level", SeniorityLevel.GRADUATE),
    ("graduate", SeniorityLevel.GRADUATE),
    ("associate", SeniorityLevel.JUNIOR),
    ("junior", SeniorityLevel.JUNIOR),
    ("mid", SeniorityLevel.MID),
    ("senior", SeniorityLevel.SENIOR),
    ("lead", SeniorityLevel.LEAD),
    ("staff", SeniorityLevel.STAFF_PLUS),
    ("principal", SeniorityLevel.STAFF_PLUS),
]


def candidate_seniority_ceiling(candidate: Candidate) -> SeniorityLevel:
    best: SeniorityLevel | None = None
    for category in candidate.preferences.preferred_job_categories:
        lowered = category.lower()
        for word, level in _SENIORITY_WORDS_BY_LEVEL:
            if word in lowered and (best is None or SENIORITY_RANK[level] > SENIORITY_RANK[best]):
                best = level
    return best or SeniorityLevel.JUNIOR


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
        if m.category in CORE_CATEGORIES
        and any(eid in project_evidence_ids for eid in m.evidence_ids)
    ]
    return _category_component("project_relevance_fit", project_backed, weight)


def _career_stage_component(
    extracted_job: ExtractedJob, candidate: Candidate, weight: float
) -> ScoreComponent | None:
    """Role level vs. the candidate's own declared target level - kept
    entirely separate from skill/technical matching (Section 2 of the
    review: "a job can be technically relevant but still unrealistic for
    me"). Returns None (drops out of the weighted average, same as any
    other under-determined component) when extraction couldn't classify
    seniority at all, rather than guessing."""
    seniority = extracted_job.seniority
    if seniority == SeniorityLevel.UNKNOWN:
        return None
    ceiling = candidate_seniority_ceiling(candidate)
    gap = SENIORITY_RANK[seniority] - SENIORITY_RANK[ceiling]
    if gap <= 0:
        raw = 100.0
    elif gap == 1:
        raw = 65.0
    elif gap == 2:
        raw = 35.0
    else:
        raw = 10.0
    return ScoreComponent(
        name="career_stage_fit",
        raw_score=raw,
        weight=weight,
        contributing_requirements=1,
        matched_requirements=1 if gap <= 0 else 0,
    )


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


def _score_caps(
    *,
    overall: float,
    extracted_job: ExtractedJob,
    matches: list[RequirementMatch],
    candidate: Candidate,
) -> tuple[float, list[str]]:
    """Deterministic downward-only adjustments for major mismatches
    (Section 5 of the review) - never raises the score, only caps it, and
    every cap that would actually constrain the raw score contributes its
    reason so the final `reasoning` string can explain what's holding a job
    back, not just report a number."""
    candidates: list[float] = []
    reasons: list[str] = []

    def _consider(cap_value: float, reason: str) -> None:
        if cap_value < overall:
            candidates.append(cap_value)
            reasons.append(reason)

    if not matches:
        _consider(
            ZERO_EVIDENCE_SCORE_CAP,
            "Little to no extractable job description content was available - this reflects "
            "low confidence, not a confirmed strong match.",
        )

    seniority = extracted_job.seniority
    if seniority != SeniorityLevel.UNKNOWN:
        ceiling = candidate_seniority_ceiling(candidate)
        gap = SENIORITY_RANK[seniority] - SENIORITY_RANK[ceiling]
        level_label = seniority.value.replace("_", " ")
        if gap >= 3:
            _consider(
                LEAD_LEVEL_SCORE_CAP,
                f"Role reads as {level_label}-level, well above your "
                f"{ceiling.value}-level target.",
            )
        elif gap == 2:
            _consider(
                SENIOR_LEVEL_SCORE_CAP,
                f"Role reads as {level_label}-level, above your {ceiling.value}-level target.",
            )

    hard_gaps = [
        m
        for m in matches
        if m.importance == RequirementImportance.REQUIRED and m.tier == EvidenceTier.NO_EVIDENCE
    ]
    if hard_gaps:
        _consider(
            HARD_GAP_SCORE_CAP,
            f"No evidence at all for a required item: {hard_gaps[0].requirement_name}.",
        )

    core_required = [
        m
        for m in matches
        if m.importance == RequirementImportance.REQUIRED and m.category in CORE_CATEGORIES
    ]
    if len(core_required) >= MIN_CORE_REQUIREMENTS_FOR_TRANSFERABLE_CAP:
        explicit_fraction = sum(
            1 for m in core_required if m.tier == EvidenceTier.EXPLICIT
        ) / len(core_required)
        if explicit_fraction < 0.5:
            _consider(
                TRANSFERABLE_MAJORITY_SCORE_CAP,
                "Most core requirements are backed only by transferable/adjacent evidence, "
                "not a direct match.",
            )

    if not candidates:
        return overall, []
    return round(min(overall, *candidates), 1), reasons


def _recommendation(overall: float, matches: list[RequirementMatch]) -> Recommendation:
    hard_gaps = [
        m
        for m in matches
        if m.importance == RequirementImportance.REQUIRED and m.tier == EvidenceTier.NO_EVIDENCE
    ]
    if hard_gaps:
        # A missing must-have caps the recommendation regardless of the
        # overall score - deterministic rule, not an LLM judgement call.
        # (`_score_caps` already pulls the numeric score down for this same
        # reason; this is the belt-and-suspenders guarantee that the
        # *label* can never say Strong Apply/Apply when one still exists.)
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
    overall: float,
    recommendation: Recommendation,
    matches: list[RequirementMatch],
    career_stage: ScoreComponent | None,
    cap_reasons: list[str],
) -> str:
    gaps = [m.requirement_name for m in matches if m.is_gap][:3]
    strengths = [
        m.requirement_name for m in matches if m.tier == EvidenceTier.EXPLICIT and not m.is_gap
    ][:3]
    parts = [f"Overall fit {overall:.0f}/100 -> {recommendation.value.replace('_', ' ').title()}."]
    if career_stage is not None:
        if career_stage.raw_score >= 100:
            parts.append("Career stage: at or below your target level.")
        elif career_stage.raw_score >= 65:
            parts.append("Career stage: one step above your target level - a reasonable stretch.")
        else:
            parts.append("Career stage: well above your target level.")
    if strengths:
        parts.append(f"Strong match on {', '.join(strengths)}.")
    if gaps:
        parts.append(f"Notable gaps: {', '.join(gaps)}.")
    parts.extend(cap_reasons)
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
            "career_stage_fit": _career_stage_component(
                extracted_job, candidate, COMPONENT_WEIGHTS["career_stage_fit"]
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
        raw_overall = sum(c.raw_score * c.weight for c in available.values()) / weight_total
        raw_overall = round(raw_overall, 1)

        overall, cap_reasons = _score_caps(
            overall=raw_overall, extracted_job=extracted_job, matches=matches, candidate=candidate
        )

        def _fallback(name: str) -> ScoreComponent:
            return ScoreComponent(
                name=name,
                raw_score=70.0,
                weight=COMPONENT_WEIGHTS[name],
                contributing_requirements=0,
                matched_requirements=0,
            )

        recommendation = _recommendation(overall, matches)
        reasoning = _reasoning(
            overall, recommendation, matches, components["career_stage_fit"], cap_reasons
        )

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
            career_stage_fit=components["career_stage_fit"],
            reasoning=reasoning,
        )
