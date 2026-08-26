"""Bounded, ranked candidate-evidence retrieval for application generation.

Every downstream application-intelligence prompt (gap strategy, application
strategy, CV tailoring, question answering, cover letters) is handed a
FIXED, bounded list of evidence produced here - never the candidate's full
profile, and never an open-ended "write about the candidate" instruction.
This is the same anti-hallucination discipline as
`app/services/matching_service.py`'s evidence whitelist, applied one step
earlier in the pipeline.

Deliberately NOT vector/embedding search, even though `EvidenceModel.embedding`
(pgvector) exists in the schema: this candidate's evidence set is small
(a personal profile, not a large corpus), already carries hand-curated
`skill_tags`, and - critically - nothing in this codebase generates
embeddings for evidence yet, so using pgvector here would mean adding a new
embedding-generation LLM call with no evidence it would outperform the
already-reliable, already-explainable tag/keyword overlap this module uses.
Simple relational matching is more reliable here; semantic retrieval is a
documented deferred enhancement for if/when the evidence set grows large
enough that hand-curated tags stop being enough (see README).
"""

from __future__ import annotations

import re
from uuid import UUID

from app.domain.candidate import Candidate, Evidence
from app.domain.job import ExtractedJob
from app.domain.matching import MatchResult

DEFAULT_MAX_EVIDENCE = 15

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.]*")


def _tokens(*texts: str | None) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        if text:
            tokens.update(_WORD_RE.findall(text.lower()))
    return tokens


def rank_evidence_for_job(
    *,
    candidate: Candidate,
    extracted_job: ExtractedJob,
    match_result: MatchResult | None = None,
    max_evidence: int = DEFAULT_MAX_EVIDENCE,
) -> list[Evidence]:
    """Ranks the candidate's evidence by relevance to one job, bounded to
    `max_evidence` items.

    Scoring signals (all deterministic, all explainable):
    - +3 per requirement this evidence was already cited for in the
      existing match_result (it's already been proven relevant once).
    - +2 per requirement-name/skill-tag token overlap with the job's
      requirements/important_phrases/role_category.
    - +1 baseline for every evidence item so nothing is ever silently
      excluded from consideration entirely.
    """
    already_cited: dict[str, int] = {}
    if match_result is not None:
        for match in match_result.matches:
            for evidence_id in match.evidence_ids:
                already_cited[str(evidence_id)] = already_cited.get(str(evidence_id), 0) + 1

    job_tokens = _tokens(
        extracted_job.role_category,
        *[r.name for r in extracted_job.requirements],
        *[r.raw_phrase for r in extracted_job.requirements],
        *extracted_job.important_phrases,
    )

    scored: list[tuple[float, Evidence]] = []
    for evidence in candidate.evidence:
        score = 1.0
        score += 3.0 * already_cited.get(str(evidence.id), 0)
        evidence_tokens = _tokens(evidence.statement, *evidence.skill_tags)
        score += 2.0 * len(evidence_tokens & job_tokens)
        scored.append((score, evidence))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [evidence for _, evidence in scored[:max_evidence]]


def evidence_by_id(candidate: Candidate, evidence_ids: list[UUID]) -> list[Evidence]:
    wanted = {str(i) for i in evidence_ids}
    return [e for e in candidate.evidence if str(e.id) in wanted]
