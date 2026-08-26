"""Explicit, single-call smoke test for the configured LLM provider.

Run this deliberately after changing ANTHROPIC_API_KEY/ANTHROPIC_MODEL to
confirm the provider actually works, without running discovery or analysing
real jobs. Makes exactly ONE structured-generation call (a trivial
extraction against a two-sentence fixture) and prints the resulting
AITrace. Never invoked automatically by discovery or the API - "having a key
configured" must never be the trigger for spending money.

Usage:
    python scripts/smoke_test_llm.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.providers.factory import get_llm_provider  # noqa: E402
from app.ai.providers.fake_provider import FakeLLMProvider  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.enums import JobSourceType  # noqa: E402
from app.domain.job import Job  # noqa: E402
from app.services.extraction_service import ExtractionService  # noqa: E402

FIXTURE_DESCRIPTION = (
    "We are hiring a Junior Python Developer. Must have Python and SQL experience. "
    "React is a bonus."
)


def main() -> int:
    settings = get_settings()
    provider = get_llm_provider()

    if isinstance(provider, FakeLLMProvider):
        print(
            "ANTHROPIC_API_KEY is not configured - get_llm_provider() returned the fake "
            "provider, so there is nothing real to smoke-test. Set the key in backend/.env "
            "and re-run this script."
        )
        return 1

    print(f"Smoke-testing model={settings.anthropic_model!r} with ONE extraction call...")

    job = Job(
        title="Junior Python Developer",
        company="Smoke Test Co",
        raw_description=FIXTURE_DESCRIPTION,
        source_type=JobSourceType.MANUAL,
    )
    service = ExtractionService(provider)

    try:
        extracted, trace = service.extract(job)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this IS the failure report
        print(f"FAILED: {exc}")
        return 1

    print("SUCCESS")
    print(f"  model: {trace.model}")
    print(f"  status: {trace.status.value}")
    print(f"  latency_ms: {trace.latency_ms}")
    print(f"  input_tokens: {trace.input_tokens}  output_tokens: {trace.output_tokens}")
    print(f"  estimated_cost_usd: {trace.estimated_cost_usd}")
    print(f"  extracted_requirements: {[r.name for r in extracted.requirements]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
