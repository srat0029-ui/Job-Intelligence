"""Per-gap application-strategy prompt, version 1."""

from app.domain.candidate import Evidence

PROMPT_VERSION = "gap_strategy_v1"

SYSTEM_PROMPT = """You are helping a real candidate prepare an honest job application. You will be
given a list of job requirements the candidate genuinely does NOT have direct evidence for, plus a
fixed list of the candidate's other evidence records (each with an id). For EACH gap requirement,
call `emit_result` with one item that:
- picks exactly one `strategy_category`: "acknowledge_honestly" (nothing adjacent - just be
  upfront), "demonstrate_transferable" (adjacent evidence exists and should be framed as
  transferable, NOT as direct experience), "provide_project_evidence" (a specific project shows
  related capability), "show_rapid_learning" (evidence of quickly picking up new tools/domains
  exists), or "do_not_address" (a minor/preferred-only gap not worth raising unprompted)
- writes one or two honest, concise sentences of `guidance` for how to frame this gap. NEVER
  suggest claiming the candidate has direct experience they do not have - guidance must always be
  honest about what is genuinely known vs. transferable vs. absent.
- sets `adjacent_evidence_ids` to ONLY ids of evidence that are genuinely relevant/transferable to
  this specific gap, copied exactly from the provided list. Empty list if nothing is relevant.

The worst failure mode here is guidance that would lead the candidate to overstate their
experience. When genuinely nothing is adjacent, say so plainly and pick "acknowledge_honestly".
"""


def build_user_prompt(*, gap_requirement_names: list[str], evidence: list[Evidence]) -> str:
    gaps_block = "\n".join(f"- {name}" for name in gap_requirement_names)
    evidence_block = "\n".join(
        f"- id={e.id} source={e.source_label!r} skill_tags={e.skill_tags} "
        f"statement={e.statement!r}"
        for e in evidence
    )
    return f"""Genuine requirement gaps to address:
{gaps_block}

Candidate's other evidence available (the ONLY evidence you may cite as adjacent):
{evidence_block}

Call `emit_result` with one item per gap listed above, in the same order."""
