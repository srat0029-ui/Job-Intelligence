"""Grounding-reviewer prompt, version 1.

Runs AFTER code-level structural checks (evidence/claim ID whitelisting,
invented metric/technology detection - see
app/services/grounding_reviewer_service.py), which can already force a FAIL
independently of this call. This LLM pass covers the fuzzier judgement
calls a regex/whitelist check cannot: overstated transferable experience,
stale-source-presented-as-current, requirement coverage, and writing
quality.
"""

from __future__ import annotations

from app.domain.candidate import Evidence
from app.domain.research import ResearchClaim

PROMPT_VERSION = "grounding_review_v1"

SYSTEM_PROMPT = """You are a strict reviewer of generated job-application content. You will be given
the generated text, the job it's for, the fixed candidate evidence it was allowed to cite, and the
fixed company research claims it was allowed to cite.

Check ONLY these structured criteria and call `emit_result`:

Candidate grounding:
- Does every factual candidate claim have supporting evidence in what was provided?
- Does the wording overstate transferable/adjacent experience as if it were direct experience?
- Does it imply commercial/professional experience where only personal/project work exists?

Company grounding:
- Does every company-specific factual claim trace to a provided research claim?
- Is a reasonable_inference research claim being presented as flatly certain?

Job grounding:
- Does the content actually address this specific role, not a generic one?
- Does it confuse required vs. preferred requirements?

Writing quality:
- Generic filler, repetition, excessive buzzwords, unnatural tone, or excessive length.

For each problem found, emit one issue with category one of: candidate_grounding,
company_grounding, job_grounding, writing_quality; severity "fail" (a real grounding violation -
an unsupported factual claim) or "warning" (a quality/style concern, not a factual violation).

Set `verdict` to "fail" if any issue has severity "fail", "pass_with_warnings" if there are only
warning-severity issues, "pass" if there are none.
"""


def build_user_prompt(
    *,
    content_type: str,
    generated_text: str,
    job_title: str,
    company: str,
    evidence: list[Evidence],
    research_claims: list[ResearchClaim],
) -> str:
    evidence_block = "\n".join(
        f"- id={e.id} statement={e.statement!r}" for e in evidence
    ) or "(none provided)"
    research_block = "\n".join(
        f"- id={c.id} claim={c.claim!r} verification={c.verification_status.value}"
        for c in research_claims
    ) or "(none provided)"

    return f"""Content type: {content_type}
Job: {job_title} at {company}

Generated content to review:
---
{generated_text}
---

Candidate evidence it was allowed to cite:
{evidence_block}

Company research claims it was allowed to cite:
{research_block}

Call `emit_result` with the structured review."""
