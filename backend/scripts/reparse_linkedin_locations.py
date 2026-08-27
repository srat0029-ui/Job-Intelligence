"""Dev-only maintenance script: corrects existing LinkedIn `discovered_jobs`
rows whose title/company/location were mis-parsed by the pre-fix parser -
a badge/status line ("Actively recruiting", "N school alumni", "N
connections", "Easy Apply", ...) got mistaken for the location, and the
company field was left holding the un-split "Company · Location" string
(see app/ingestion/linkedin_email_parser.py's module docstring for the full
root cause and fix).

Scope, deliberately narrow: only rows with status == prefilter_rejected AND
geographic_eligibility != eligible are touched - by construction of
DiscoveryService._process_posting, a row can only be geo-rejected if the
geo gate ran and failed, and a row that's already `analysed`/`analysing`/
`eligible` has real downstream state (a linked `Job`, real user/application
activity) this script must never disturb. Nothing is deleted or recreated:
each row is matched to its origin by (source='linkedin', external_id=job
id) and updated in place - `created_at`/`first_seen_at`/`reviewed_at`/
`job_id`/SourceObservation audit rows are never touched.

For each affected row:
  1. Re-fetch its origin Gmail message (read-only, via the stored
     gmail_message_id) and re-parse it with the FIXED parser.
  2. If the freshly-parsed title/company/location/description differ from
     what's stored, update them in place, and recompute the dedup
     fingerprints so future syncs still match this corrected row instead of
     creating a duplicate.
  3. Re-run geographic eligibility (location_service.normalize_location) on
     the corrected location - never just flip LOCATION_UNCONFIRMED to
     eligible without the underlying value actually being fixed first.
  4. If now eligible, re-run the exact same relevance gate
     (evaluate_relevance) DiscoveryService._process_posting would have run
     next - a newly-eligible-but-irrelevant job stays rejected (now for the
     real relevance reason instead of the old geo reason), never
     auto-promoted.
  5. If eligible AND relevant, promote+analyse through the exact same
     `DiscoveryService.promote_and_analyze` path the automated analysis
     phase and the manual "force analyse" endpoint both use - subject to
     the same max_ai_analyses_per_run / daily budget caps (checked here the
     same way `_run_analysis_phase` does).

Usage:
    python scripts/reparse_linkedin_locations.py            # apply
    python scripts/reparse_linkedin_locations.py --dry-run
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.ai.providers.factory import get_llm_provider  # noqa: E402
from app.db.models.discovery import DiscoveredJobModel  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.domain.enums import DiscoveredJobStatus, GeographicEligibility  # noqa: E402
from app.ingestion.gmail_client import GmailClient  # noqa: E402
from app.ingestion.job_page_enrichment import enrich_posting  # noqa: E402
from app.ingestion.job_source import RawJobPosting  # noqa: E402
from app.ingestion.linkedin_email_parser import parse_linkedin_alert_email  # noqa: E402
from app.repositories.ai_trace_repository import AITraceRepository  # noqa: E402
from app.repositories.app_settings_repository import AppSettingsRepository  # noqa: E402
from app.repositories.candidate_repository import CandidateRepository  # noqa: E402
from app.repositories.gmail_credential_repository import GmailCredentialRepository  # noqa: E402
from app.services import deduplication_service, location_service  # noqa: E402
from app.services.analysis_priority_service import compute_analysis_priority  # noqa: E402
from app.services.discovery_service import DiscoveryService  # noqa: E402
from app.services.gmail_auth_service import GmailAuthService  # noqa: E402
from app.services.relevance_service import evaluate_relevance  # noqa: E402

CORRECTABLE_STATUSES = (DiscoveredJobStatus.PREFILTER_REJECTED.value,)


def _fresh_postings_by_message(
    db: Session, message_ids: set[str]
) -> dict[str, dict[str, RawJobPosting]]:
    cred_repo = GmailCredentialRepository()
    auth = GmailAuthService()
    credential = cred_repo.get(db)
    if credential is None:
        raise SystemExit("Gmail is not connected.")

    refresh_token = auth.decrypt(credential.refresh_token_encrypted)
    access_token, _ = auth.refresh_access_token(refresh_token)
    client = GmailClient(access_token=access_token)

    result: dict[str, dict[str, RawJobPosting]] = {}
    for message_id in message_ids:
        try:
            message = client.get_message(message_id)
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the rest
            print(f"  ! failed to fetch {message_id}: {exc}")
            continue
        if not message.html_body:
            continue
        postings = parse_linkedin_alert_email(
            message.html_body, message_id=message_id, received_at=message.received_at
        )
        result[message_id] = {p.external_id: p for p in postings if p.external_id}
    return result


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    suffix = " (dry run)" if dry_run else ""

    db = SessionLocal()
    try:
        candidate = CandidateRepository().get_singleton(db)
        if candidate is None:
            raise SystemExit("No candidate profile exists yet - cannot evaluate relevance.")
        app_settings = AppSettingsRepository().get(db)
        ai_trace_repo = AITraceRepository()
        service = DiscoveryService(llm_provider=get_llm_provider())

        affected = list(
            db.execute(
                select(DiscoveredJobModel).where(
                    DiscoveredJobModel.source == "linkedin",
                    DiscoveredJobModel.status.in_(CORRECTABLE_STATUSES),
                    DiscoveredJobModel.geographic_eligibility
                    != GeographicEligibility.ELIGIBLE.value,
                )
            )
            .scalars()
            .all()
        )
        message_ids: set[str] = {
            mid
            for m in affected
            if (mid := (m.source_metadata or {}).get("gmail_message_id")) is not None
        }
        print(
            f"Affected rows: {len(affected)} across {len(message_ids)} LinkedIn message(s){suffix}"
        )

        fresh_by_message = _fresh_postings_by_message(db, message_ids)

        corrected = 0
        now_eligible = 0
        still_unconfirmed = 0
        now_ineligible = 0
        promoted_for_analysis = 0
        skipped_irrelevant = 0
        analysed = 0
        failed_analysis = 0
        no_fresh_data = 0

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent_today = ai_trace_repo.sum_cost_since(db, today_start)
        analyses_this_run = 0

        for model in affected:
            gmail_message_id = str((model.source_metadata or {}).get("gmail_message_id") or "")
            fresh = fresh_by_message.get(gmail_message_id, {}).get(model.external_id or "")
            if fresh is None:
                no_fresh_data += 1
                continue

            changed = (
                fresh.title != model.title
                or fresh.company != model.company
                or fresh.location != model.location
            )
            if changed:
                corrected += 1
                print(
                    f"  [{model.company!r} -> {fresh.company!r}] "
                    f"location={model.location!r} -> {fresh.location!r}"
                )

            eligibility = location_service.normalize_location(
                location=fresh.location,
                description=fresh.raw_description,
                remote_type=fresh.remote_type,
            )

            if dry_run:
                if eligibility.eligibility == GeographicEligibility.ELIGIBLE:
                    now_eligible += 1
                elif eligibility.eligibility == GeographicEligibility.LOCATION_UNCONFIRMED:
                    still_unconfirmed += 1
                else:
                    now_ineligible += 1
                continue

            model.title = fresh.title
            model.company = fresh.company
            model.location = fresh.location
            model.raw_description = fresh.raw_description
            model.dedupe_fingerprint = deduplication_service.compute_fingerprint(fresh)
            model.description_fingerprint = deduplication_service.description_fingerprint(
                fresh.raw_description
            )
            model.country = eligibility.country
            model.geographic_eligibility = eligibility.eligibility.value
            model.geographic_eligibility_reason = eligibility.reason

            if eligibility.eligibility != GeographicEligibility.ELIGIBLE:
                if eligibility.eligibility == GeographicEligibility.LOCATION_UNCONFIRMED:
                    still_unconfirmed += 1
                else:
                    now_ineligible += 1
                model.status = DiscoveredJobStatus.PREFILTER_REJECTED.value
                model.prefilter_reason = eligibility.reason
                db.flush()
                continue

            now_eligible += 1
            relevance = evaluate_relevance(fresh, candidate)
            if not relevance.passed:
                skipped_irrelevant += 1
                model.status = DiscoveredJobStatus.PREFILTER_REJECTED.value
                model.prefilter_reason = relevance.reason
                db.flush()
                continue

            enriched = enrich_posting(fresh)
            model.raw_description = enriched.raw_description
            model.description_fingerprint = deduplication_service.description_fingerprint(
                enriched.raw_description
            )
            model.status = DiscoveredJobStatus.AWAITING_ANALYSIS.value
            model.prefilter_reason = None
            model.analysis_priority = compute_analysis_priority(
                posting=enriched,
                search_profile=None,
                watchlist_entry=None,
                candidate_preferred_locations=candidate.preferences.preferred_locations,
            )
            promoted_for_analysis += 1
            db.flush()

            budget = app_settings.daily_ai_analysis_budget_usd
            if analyses_this_run >= app_settings.max_ai_analyses_per_run:
                continue
            if budget is not None and spent_today >= budget:
                continue
            try:
                job, _priority = service.promote_and_analyze(db, model)
                analysed += 1
                analyses_this_run += 1
                traces = ai_trace_repo.list_for_input(db, str(job.id))
                spent_today += sum(t.estimated_cost_usd or 0.0 for t in traces)
            except Exception as exc:  # noqa: BLE001 - isolate one bad job from the rest
                failed_analysis += 1
                model.status = DiscoveredJobStatus.ANALYSIS_FAILED.value
                model.source_metadata = {
                    **(model.source_metadata or {}),
                    "analysis_error": str(exc)[:500],
                }
                db.flush()
                print(f"  ! analysis failed for {model.title!r}: {exc}")

        if not dry_run:
            db.commit()

        print()
        print("Summary:")
        print(f"  Affected rows found: {len(affected)}")
        print(f"  No fresh data available (message fetch failed): {no_fresh_data}")
        print(f"  Rows with corrected title/company/location: {corrected}")
        print(f"  Now geographically eligible: {now_eligible}")
        print(f"  Still location_unconfirmed: {still_unconfirmed}")
        print(f"  Now classified ineligible (overseas): {now_ineligible}")
        print(f"  Promoted to awaiting_analysis: {promoted_for_analysis}")
        print(f"  Rejected as irrelevant after becoming eligible: {skipped_irrelevant}")
        print(f"  Analysed this run: {analysed}")
        print(f"  Analysis failures: {failed_analysis}")
        if dry_run:
            print("\nDry run - no changes were committed. Re-run without --dry-run to apply.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
