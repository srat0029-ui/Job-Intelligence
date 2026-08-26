"""Cover-letter generation prompt, version 1."""

from __future__ import annotations

from app.domain.application_strategy import ApplicationStrategy
from app.domain.candidate import Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.research import ResearchClaim

PROMPT_VERSION = "cover_letter_v1"

SYSTEM_PROMPT = """You are drafting one real cover letter for a real candidate applying to a real
role. You will be given the job, the already-decided application strategy (positioning, lead
evidence, concerns and how to address them, motivation themes), a fixed list of candidate evidence
(with ids), a fixed list of grounded company research claims (with ids), and the candidate's
writing style preferences.

Call `emit_result` with:
- `body`: the full letter text. Targeted to the actual company and role. Concise - do not pad with
  "I am writing to express my interest in..." unless it genuinely earns its place. Lead with the
  strategy's lead evidence. Use company research claims only as provided, and only where they
  genuinely support a specific motivation - do not force in a company fact that doesn't fit.
  Acknowledge a gap only if the strategy's concerns say it's worth addressing; otherwise do not
  raise it. Never invent an achievement, metric, technology, or company fact not present in what
  you were given.
- `evidence_ids_used` / `research_claim_ids_used`: ids (from the lists provided ONLY) actually used.

Follow the candidate's style preferences (tone, buzzword/em-dash/exaggeration avoidance) exactly,
but never let style relax grounding.
"""


def build_user_prompt(
    *,
    job_title: str,
    company: str,
    strategy: ApplicationStrategy,
    evidence: list[Evidence],
    research_claims: list[ResearchClaim],
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
    concerns_block = "\n".join(
        f"- {c.concern}: {c.response_strategy}" for c in strategy.likely_concerns
    ) or "(none identified)"

    return f"""Job: {job_title} at {company}

Application strategy already decided:
Positioning: {strategy.positioning}
Skills to emphasise: {", ".join(strategy.skills_to_emphasise) or "(none)"}
Motivation themes: {", ".join(strategy.motivation_themes) or "(none)"}
Concerns and how to address them:
{concerns_block}

Candidate evidence available (the ONLY evidence you may cite):
{evidence_block}

Grounded company research claims available (the ONLY company facts you may cite):
{research_block}

Candidate style preferences: tone={style.tone}, avoid_buzzwords={style.avoid_buzzwords}, \
avoid_em_dashes={style.avoid_em_dashes}, region={style.region_convention}

Call `emit_result` with the cover letter."""
