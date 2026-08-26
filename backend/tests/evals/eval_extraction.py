"""Live extraction-accuracy eval - answers "how accurately does the
extractor identify requirements?" using real fixtures and the real
Anthropic provider.

Not a pytest test: it costs real tokens and needs ANTHROPIC_API_KEY, so it's
a script you run deliberately, not part of the default `pytest` run.

Usage:
    cd backend
    python -m tests.evals.eval_extraction

For each fixture, computes:
- required-skill recall: fraction of expected required skills the extractor
  actually surfaced (as a required OR preferred requirement - missing it
  entirely is the failure mode that matters most)
- precision proxy: fraction of extracted requirements that match something
  in the expected set (a rough signal for over-extraction/noise; not a
  strict metric since expected lists are deliberately non-exhaustive)
- role_category keyword hit: whether the inferred role_category contains at
  least one expected keyword

This is intentionally simple (substring matching, not embeddings) - good
enough to catch regressions in prompt changes without building a labelled
gold-standard dataset that doesn't exist yet.
"""

from __future__ import annotations

import sys

from app.ai.providers.factory import get_llm_provider
from app.core.config import get_settings
from app.domain.enums import JobSourceType
from app.domain.job import Job
from app.services.extraction_service import ExtractionService
from tests.evals.fixtures import load_fixtures


def _normalise(text: str) -> str:
    return text.lower().strip()


def _recall(expected: list[str], extracted_names: list[str]) -> float:
    if not expected:
        return 1.0
    extracted_norm = [_normalise(n) for n in extracted_names]
    hits = sum(
        1
        for e in expected
        if any(_normalise(e) in n or n in _normalise(e) for n in extracted_norm)
    )
    return hits / len(expected)


def main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY not set - skipping live extraction eval.")
        print("Set it in backend/.env and re-run: python -m tests.evals.eval_extraction")
        return 0

    fixtures = load_fixtures()
    service = ExtractionService(get_llm_provider())

    results = []
    for fixture in fixtures:
        job = Job(
            title=fixture.title,
            company=fixture.company,
            location=fixture.location,
            raw_description=fixture.raw_description,
            source_type=JobSourceType.MANUAL,
        )
        extracted, trace = service.extract(job)
        all_names = [r.name for r in extracted.requirements]

        required_recall = _recall(fixture.expected_required_skills, all_names)
        preferred_recall = _recall(fixture.expected_preferred_skills, all_names)
        role_hit = any(
            kw.lower() in (extracted.role_category or "").lower()
            for kw in fixture.expected_role_category_keywords
        )

        results.append(
            (fixture.name, required_recall, preferred_recall, role_hit, trace.latency_ms)
        )
        print(
            f"[{fixture.name}] required_recall={required_recall:.2f} "
            f"preferred_recall={preferred_recall:.2f} role_category_hit={role_hit} "
            f"latency_ms={trace.latency_ms} tokens_in={trace.input_tokens} "
            f"tokens_out={trace.output_tokens}"
        )

    avg_required = sum(r[1] for r in results) / len(results)
    avg_preferred = sum(r[2] for r in results) / len(results)
    role_hit_rate = sum(1 for r in results if r[3]) / len(results)
    print("\n--- Summary ---")
    print(f"avg required-skill recall: {avg_required:.2f}")
    print(f"avg preferred-skill recall: {avg_preferred:.2f}")
    print(f"role_category keyword hit rate: {role_hit_rate:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
