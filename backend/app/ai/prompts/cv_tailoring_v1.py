"""CV tailoring-suggestion prompt, version 1."""

from __future__ import annotations

from app.domain.candidate import Evidence, Project, Skill, WorkExperience
from app.domain.communication_style import CommunicationStyle

PROMPT_VERSION = "cv_tailoring_v1"

SYSTEM_PROMPT = """You are helping tailor a real candidate's CV to one specific job, WITHOUT
inventing anything. You will be given the candidate's existing projects/work experience/skills
(their real, current wording) and a fixed list of relevant evidence (with ids).

For a handful of the most relevant existing bullets/entries, call `emit_result` with a suggestion
that:
- copies `original_text` EXACTLY from what was provided - never paraphrase this field.
- writes a `suggested_text` that reorders emphasis, tightens wording, or foregrounds relevant
  detail ALREADY PRESENT in original_text or in the cited evidence statements - it must NEVER add
  a technology, tool, metric/number, or achievement that is not already stated in original_text or
  in a cited evidence statement. Do not invent outcomes, percentages, team sizes, or timeframes.
- sets `supporting_evidence_ids` to ids (from the provided list ONLY) that back this specific
  suggestion.
- gives each a `relevance_rank` (1 = most relevant to this job).

Also suggest a `section_emphasis` order (e.g. which of projects/skills/employment to lead with)
for this specific job.

The worst failure mode is a suggested bullet that reads as more impressive or more specific than
what the candidate can actually support - when in doubt, stay closer to the original wording.
"""


def build_user_prompt(
    *,
    job_title: str,
    company: str,
    projects: list[Project],
    work_history: list[WorkExperience],
    skills: list[Skill],
    evidence: list[Evidence],
    style: CommunicationStyle,
) -> str:
    projects_block = "\n".join(
        f"- name={p.name!r} description={p.description!r} technologies={p.technologies} "
        f"highlights={p.highlights}"
        for p in projects
    ) or "(none)"
    work_block = "\n".join(
        f"- company={w.company!r} title={w.title!r} summary={w.summary!r} "
        f"technologies={w.technologies}"
        for w in work_history
    ) or "(none)"
    skills_block = ", ".join(s.name for s in skills) or "(none)"
    evidence_block = "\n".join(
        f"- id={e.id} source={e.source_label!r} skill_tags={e.skill_tags} "
        f"statement={e.statement!r}"
        for e in evidence
    )

    return f"""Job: {job_title} at {company}

Candidate's existing projects:
{projects_block}

Candidate's existing work history:
{work_block}

Candidate's declared skills: {skills_block}

Candidate evidence available (the ONLY evidence you may cite):
{evidence_block}

Candidate style preferences: tone={style.tone}, \
avoid_exaggerated_claims={style.avoid_exaggerated_claims}

Call `emit_result` with tailoring suggestions for the most relevant entries only."""
