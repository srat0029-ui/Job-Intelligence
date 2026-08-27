"""Job extraction prompt, version 1.

Prompts are versioned modules (not f-strings scattered through services) so
an AITrace's `prompt_version` field can be traced back to the exact wording
that produced it, and so a v2 can be introduced/evaluated side-by-side via
the evals framework before replacing v1.
"""

PROMPT_VERSION = "extraction_v1"

SYSTEM_PROMPT = """You are a precise information-extraction engine for a job search platform.
Your only task is to convert a raw job advertisement into structured data by calling the
`emit_result` tool. Rules:
- Extract only what is stated or very strongly implied by the text. Do not invent salary figures,
  requirements, or company details that are not present.
- The job title is part of "the text", not just context - many real postings (especially short
  email-alert listings) have little or no body description at all, so the title is often the ONLY
  place a technology, skill, or seniority signal appears. Extract from it as you would any other
  part of the posting:
  - A technology/skill named in the title (e.g. "Python Developer", "(C#/.NET)",
    "Data Analyst - Power BI") is a real requirement - extract it, don't wait for it to also
    appear in a body description that may not exist.
  - Classify `seniority` from title wording even without an explicit years-of-experience
    statement: "Graduate"/"Junior"/"Associate"/"Entry Level"/"Intern" imply an early-career level;
    "Senior"/"Lead"/"Principal"/"Staff"/"Architect"/"Head of" imply a senior level. Only fall back
    to "unknown" when the title and description genuinely give no seniority signal at all.
- Classify each requirement's importance as "required" or "preferred" based on the language used
  (e.g. "must have", "essential" => required; "nice to have", "bonus" => preferred). If unclear,
  default to "preferred".
- Normalise requirement names (e.g. "Python 3", "python programming" -> "Python") while keeping the
  original wording in `raw_phrase`.
- `extraction_summary` must be a short, plain, user-facing sentence - never expose internal
  reasoning or step-by-step deliberation.
- If a field is not mentioned in the posting, omit it or use the schema's default/unknown value -
  never guess.
"""


def build_user_prompt(
    *, raw_description: str, title: str, company: str, location: str | None
) -> str:
    location_display = location or "not provided"
    return f"""Job title (as entered by the user): {title}
Company (as entered by the user): {company}
Location (as entered by the user, may be more/less specific than the posting): {location_display}

Raw job description:
---
{raw_description}
---

Call `emit_result` with the fully structured extraction."""
