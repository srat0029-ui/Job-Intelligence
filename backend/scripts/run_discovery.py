"""Runs one discovery cycle without the frontend: fetches jobs for every
enabled search profile, normalises, dedupes, pre-filters, and (subject to
the configured cost controls) analyses the eligible ones through the
existing extraction/matching/scoring pipeline.

Usage:
    python scripts/run_discovery.py                  # all enabled profiles
    python scripts/run_discovery.py <profile-uuid> ...  # only these profiles

This is the same DiscoveryService the API's `POST /api/discovery/run` uses
- there is exactly one discovery implementation, callable from either the
UI or the command line.
"""

import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.providers.factory import get_llm_provider  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.analysis_orchestrator import CandidateProfileMissingError  # noqa: E402
from app.services.discovery_service import DiscoveryService, NoSearchProfilesError  # noqa: E402


def main() -> int:
    profile_ids = [UUID(arg) for arg in sys.argv[1:]] or None

    db = SessionLocal()
    try:
        service = DiscoveryService(llm_provider=get_llm_provider())
        try:
            run = service.run(db, search_profile_ids=profile_ids)
        except CandidateProfileMissingError as exc:
            print(f"Cannot run discovery: {exc}")
            return 1
        except NoSearchProfilesError as exc:
            print(f"Cannot run discovery: {exc}")
            return 1

        c = run.counts
        print("Discovery complete")
        print(f"  Status: {run.status.value}")
        print(f"  Retrieved: {c.retrieved}")
        print(f"  New: {c.new}")
        print(f"  Duplicates: {c.duplicates}")
        print(f"  Pre-filter rejected: {c.prefilter_rejected}")
        print(f"  Eligible: {c.eligible}")
        print(f"  AI analysed: {c.analysed}")
        print(f"  Deferred due to run/budget limit: {c.deferred}")
        print(f"  Failed: {c.failed}")
        print(f"  Strong Apply+: {c.strong_apply_or_better}")
        print(f"  Estimated AI cost: ${run.estimated_cost_usd:.4f}")
        if run.error_message:
            print(f"  Error: {run.error_message}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
