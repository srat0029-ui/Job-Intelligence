"""Application strategy synthesis prompt, version 1."""

from __future__ import annotations

from app.domain.candidate import Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.gap_analysis import GapStrategyItem
from app.domain.research import ResearchClaim

PROMPT_VERSION = "application_strategy_v1"

SYSTEM_PROMPT = """You are helping a real candidate build an honest, evidence-grounded strategy for
one specific job application. You will be given: the job's title/company/responsibilities, a fixed
list of the candidate's evidence (with ids), a fixed list of grounded company research claims (with
ids), the results of gap analysis (how genuine gaps should be framed), and the candidate's writing
style preferences.

Call `emit_result` with:
- `positioning`: 1-3 sentences on the strongest honest way to position this candidate for this role.
- `lead_evidence_ids`: 2-4 ids (from the evidence list ONLY) that should dominate the application -
  the strongest, most relevant items.
- `skills_to_emphasise` / `skills_to_deemphasise`: short skill/tech names.
- `likely_concerns`: concerns a recruiter might reasonably have, each with an honest
  `response_strategy` - reuse the provided gap-analysis guidance where a concern maps to a genuine
  gap; do not invent concerns unconnected to the actual job/profile.
- `motivation_themes`: genuine connections between the candidate's evidence, this role, and the
  company research claims provided ONLY - never invent a company fact or a candidate motivation not
  supported by what you were given.

Respect the candidate's style preferences (tone, buzzword/exaggeration avoidance) in HOW you write
`positioning` and the concern/motivation text, but never let style relax grounding: every company
fact must trace to a provided research claim, every candidate claim to provided evidence.
"""


def build_user_prompt(
    *,
    job_title: str,
    company: str,
    role_category: str | None,
    responsibilities: list[str],
    evidence: list[Evidence],
    research_claims: list[ResearchClaim],
    gap_strategies: list[GapStrategyItem],
    style: CommunicationStyle,
) -> str:
    evidence_block = "\n".join(
        f"- id={e.id} source={e.source_label!r} skill_tags={e.skill_tags} "
        f"statement={e.statement!r}"
        for e in evidence
    )
    research_block = (
        "\n".join(f"- id={c.id} category={c.category} claim={c.claim!r}" for c in research_claims)
        or "(no research claims available)"
    )
    gaps_block = (
        "\n".join(
            f"- {g.requirement_name}: category={g.strategy_category.value} guidance={g.guidance!r}"
            for g in gap_strategies
        )
        or "(no significant gaps identified)"
    )
    responsibilities_block = "\n".join(f"- {r}" for r in responsibilities) or "(none extracted)"

    return f"""Job: {job_title} at {company}
Role category: {role_category or "unknown"}
Responsibilities:
{responsibilities_block}

Candidate evidence available (the ONLY evidence you may cite):
{evidence_block}

Grounded company research claims available (the ONLY company facts you may cite):
{research_block}

Gap analysis results (reuse this framing for concerns tied to these gaps):
{gaps_block}

Candidate style preferences: tone={style.tone}, avoid_buzzwords={style.avoid_buzzwords}, \
avoid_exaggerated_claims={style.avoid_exaggerated_claims}, region={style.region_convention}

Call `emit_result` with the application strategy."""
