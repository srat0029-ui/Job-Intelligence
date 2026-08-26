"""Application-question response generation prompt, version 1.

Classification happens deterministically in code before this prompt is ever
built - see app/services/application_question_service.py.
"""

from __future__ import annotations

from app.domain.candidate import Evidence
from app.domain.communication_style import CommunicationStyle
from app.domain.research import ResearchClaim

PROMPT_VERSION = "application_question_v1"

SYSTEM_PROMPT = """You are drafting one honest answer to a real job-application question, for a real
candidate. You will be given the question, its classification, the job context, a fixed list of
candidate evidence (with ids), a fixed list of grounded company research claims (with ids), and the
candidate's writing style preferences.

Call `emit_result` with:
- `response_text`: a concise, first-person, honest draft answer. Use only concrete examples that
  are actually supported by the provided evidence - never invent an example, project, or outcome.
  Reference company facts ONLY from the provided research claims.
- `evidence_ids_used` / `research_claim_ids_used`: the ids (from the lists provided ONLY) that this
  answer actually draws on.

Respect the candidate's style preferences in tone, but never let style relax grounding - do not
pad with generic filler ("I am a hardworking team player...") when the same space could be spent on
a real, evidence-backed example.
"""


def build_user_prompt(
    *,
    question_text: str,
    classifications: list[str],
    job_title: str,
    company: str,
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
    return f"""Question: {question_text!r}
Classified as: {", ".join(classifications) or "general_background"}
Job: {job_title} at {company}

Candidate evidence available (the ONLY evidence you may cite):
{evidence_block}

Grounded company research claims available (the ONLY company facts you may cite):
{research_block}

Candidate style preferences: tone={style.tone}, avoid_buzzwords={style.avoid_buzzwords}

Call `emit_result` with the draft answer."""
