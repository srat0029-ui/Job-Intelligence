"""Requirement-matching prompt, version 1.

The anti-hallucination guarantee lives partly here (explicit instruction)
and partly in code (MatchingService strips any evidence_id the model returns
that wasn't actually offered to it - see app.services.matching_service).
Prompts alone are not trusted as the enforcement mechanism.
"""

from app.domain.candidate import Evidence
from app.domain.job import ExtractedRequirement

PROMPT_VERSION = "matching_v1"

SYSTEM_PROMPT = """You are a strict evidence-matching engine for a job search platform. You will be
given a list of job requirements and a fixed list of candidate evidence records (each with an id).
For EACH requirement, call `emit_result` with one match object that:
- classifies the evidence tier as one of: "explicit" (the evidence directly names this skill/tech
  or an unambiguous synonym), "transferable" (related/adjacent evidence that would plausibly
  transfer), "weak_inference" (only a thin, indirect signal), or "no_evidence" (nothing supports it)
- sets `evidence_ids` to ONLY the ids of evidence records that genuinely support the requirement,
  copied exactly from the provided list. NEVER invent an id. NEVER cite evidence whose content does
  not actually support the requirement just to avoid a gap. If nothing supports it, return an empty
  list and tier "no_evidence".
- gives a `confidence` between 0 and 1 reflecting how sure you are of the tier classification itself
  (not how good the candidate is)
- gives a one-sentence, user-facing `evidence_summary` with no internal reasoning or hedging filler

You are matching against a real candidate's real background. Fabricating experience they do not
have is the single worst failure mode of this system - when in doubt, classify lower, not higher.
"""


def build_user_prompt(
    *, requirements: list[ExtractedRequirement], evidence: list[Evidence]
) -> str:
    requirements_block = "\n".join(
        f"- name={r.name!r} category={r.category.value} importance={r.importance.value} "
        f"raw_phrase={r.raw_phrase!r}"
        for r in requirements
    )
    evidence_block = "\n".join(
        f"- id={e.id} source={e.source_label!r} skill_tags={e.skill_tags} "
        f"statement={e.statement!r}"
        for e in evidence
    )
    return f"""Job requirements to match:
{requirements_block}

Candidate evidence available (the ONLY evidence you may cite):
{evidence_block}

Call `emit_result` with one match entry per requirement listed above, in the same order."""
