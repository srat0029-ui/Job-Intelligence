"""One-off maintenance script: re-evaluates geographic eligibility for every
existing `discovered_jobs` row against the current `location_service` rules.

Needed because the Australia-eligibility gate (see
app/services/location_service.py) was added after this project already had
discovered jobs in the database - those rows default to
`location_unconfirmed` (see the migration), which already keeps them out of
the recommended feed, but this script computes their REAL eligibility so the
data is honestly classified rather than just defaulted.

A row found to be non-Australian is reclassified to `PREFILTER_REJECTED`
(reusing the existing status, exactly as a freshly-discovered ineligible
posting would be) ONLY if it hasn't already been promoted/analysed -
`analysed`/`analysing` rows are left with their existing status (their
`Job`/`JobAnalysis` records are real work product, kept for audit) but still
get their `geographic_eligibility`/`country`/`geographic_eligibility_reason`
columns corrected, which is what actually removes them from the recommended
feed (`list_paginated` filters on `geographic_eligibility`, not `status`,
for this).

Nothing is deleted. Usage:

    python scripts/backfill_location_eligibility.py         # apply
    python scripts/backfill_location_eligibility.py --dry-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.domain.enums import GeographicEligibility  # noqa: E402
from app.repositories.discovered_job_repository import DiscoveredJobRepository  # noqa: E402
from app.services import location_service  # noqa: E402


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    repo = DiscoveredJobRepository()

    db = SessionLocal()
    try:
        models = repo.list_all_models(db)
        suffix = " (dry run)" if dry_run else ""
        print(f"Re-evaluating {len(models)} discovered_jobs row(s){suffix}...")

        changed = 0
        reclassified_status = 0
        by_new_eligibility: dict[str, int] = {}

        for model in models:
            result = location_service.normalize_location(
                location=model.location,
                description=model.raw_description,
                remote_type=model.remote_type,
            )
            by_new_eligibility[result.eligibility.value] = (
                by_new_eligibility.get(result.eligibility.value, 0) + 1
            )
            if (
                model.country == result.country
                and model.geographic_eligibility == result.eligibility.value
            ):
                continue

            changed += 1
            was_active = model.status in ("discovered", "awaiting_analysis")
            print(
                f"  [{model.company}] {model.title!r} location={model.location!r}: "
                f"{model.geographic_eligibility} -> {result.eligibility.value} ({result.reason})"
            )
            if not dry_run:
                repo.set_geographic_eligibility(
                    db,
                    model.id,
                    country=result.country,
                    geographic_eligibility=result.eligibility,
                    geographic_eligibility_reason=result.reason,
                )
            if was_active and result.eligibility != GeographicEligibility.ELIGIBLE:
                reclassified_status += 1

        if not dry_run:
            db.commit()

        print()
        print("Summary:")
        for eligibility, count in sorted(by_new_eligibility.items()):
            print(f"  {eligibility}: {count}")
        print(f"  Rows updated: {changed}")
        print(
            "  Rows reclassified from discovered/awaiting_analysis to "
            f"prefilter_rejected: {reclassified_status}"
        )
        if dry_run:
            print("\nDry run - no changes were committed. Re-run without --dry-run to apply.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
