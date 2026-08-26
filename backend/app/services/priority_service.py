"""Discovery-feed priority classification and "why this job" summaries.

Both functions here are pure and derive everything from an already-computed
`JobAnalysis` (extraction + match_result + fit_score) - no LLM call, no new
candidate claims. `classify_priority` is deliberately a separate concept
from `FitScore.recommendation`: the latter is gap-aware (a missing required
skill caps it regardless of score - see ScoringService), while priority is
a plain, score-only bucket meant for skimming a long ranked feed at a
glance. Thresholds are named constants, not magic numbers, and never chosen
by the LLM.
"""

from __future__ import annotations

from app.domain.analysis import JobAnalysis
from app.domain.enums import EvidenceTier, JobPriority, RequirementImportance

# Must stay sorted descending by threshold - classify_priority relies on it.
PRIORITY_THRESHOLDS: list[tuple[float, JobPriority]] = [
    (90.0, JobPriority.APPLY_ASAP),
    (80.0, JobPriority.STRONG_APPLY),
    (70.0, JobPriority.APPLY),
    (60.0, JobPriority.STRETCH),
]
DEFAULT_PRIORITY = JobPriority.LOW_PRIORITY


def classify_priority(overall_score: float) -> JobPriority:
    for threshold, priority in PRIORITY_THRESHOLDS:
        if overall_score >= threshold:
            return priority
    return DEFAULT_PRIORITY


def build_why_summary(analysis: JobAnalysis, max_bullets: int = 5) -> list[str]:
    """A short bullet list explaining an analysis's recommendation, built
    entirely from fields already stored on the JobAnalysis - every claim
    here is traceable back to a RequirementMatch or ScoreComponent that's
    already in the database, never a fresh model call."""
    matches = analysis.match_result.matches
    bullets: list[str] = []

    strong = [
        m.requirement_name
        for m in matches
        if m.tier == EvidenceTier.EXPLICIT and not m.is_gap
    ]
    if strong:
        shown = ", ".join(strong[:3])
        bullets.append(f"Strong, evidence-backed match on {shown}.")

    seniority = analysis.extracted_job.seniority.value
    if seniority in ("intern", "graduate", "junior"):
        bullets.append(f"Seniority looks like a {seniority}-level role.")

    if analysis.fit_score.location_fit.raw_score >= 90:
        bullets.append("Location matches your stated preferences.")

    if analysis.fit_score.project_relevance_fit.matched_requirements > 0:
        bullets.append(
            f"{analysis.fit_score.project_relevance_fit.matched_requirements} requirement(s) "
            "are backed directly by your project evidence, not just declared skills."
        )

    required_gaps = [
        m.requirement_name
        for m in matches
        if m.is_gap and m.importance == RequirementImportance.REQUIRED
    ]
    other_gaps = [m.requirement_name for m in matches if m.is_gap and m not in required_gaps]
    if required_gaps:
        bullets.append(f"Main gap: {required_gaps[0]} (required).")
    elif other_gaps:
        bullets.append(f"Only gap: {other_gaps[0]} (preferred, not required).")
    elif not any(m.is_gap for m in matches):
        bullets.append("No identified gaps against the extracted requirements.")

    return bullets[:max_bullets]
