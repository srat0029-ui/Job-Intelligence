"""Dev-only maintenance script for the recommendation-quality fix (role-
family matching + deterministic fit-scoring).

Two phases, matching the task's "re-evaluate the REAL current jobs" ask:

PHASE A - re-score every existing analysed job with the new deterministic
`ScoringService` (no new LLM calls) using its ALREADY-STORED extraction and
match result. For jobs whose stored `raw_description` was corrupted by the
LinkedIn-login-wall enrichment bug (see job_page_enrichment.py's fix) - a
real, identifiable defect, not a guess: every corrupted row shares the
exact same "We're signing you in" chrome text - purely deterministic
re-scoring of that garbage can only ever produce a low-confidence number
(correctly, via the new zero-evidence cap), never a genuinely differentiated
one. For those specific rows only, this additionally restores the real
alert-email content (re-fetched from the original Gmail source, same
technique as the SEEK/LinkedIn parser-fix scripts) and re-runs
extraction+matching - new LLM calls, but necessary ones: no purely
deterministic re-scoring of a page that was never actually the job can
honestly tell an architect role from a graduate role.

PHASE B - re-evaluates every DiscoveredJob currently `prefilter_rejected`
for "no target role family matched" against the NEW relevance_service logic
(the broadened role families + generic graduate-program fallback). Jobs
that now pass are promoted through the exact same
`DiscoveryService.promote_and_analyze` path used everywhere else, subject
to the same max_ai_analyses_per_run / daily budget caps. Jobs that still
don't pass are left untouched - this does NOT broaden every rejected job,
only re-checks the ones rejected specifically for role-family reasons.

Nothing is deleted. A new JobAnalysisModel row is saved for every
re-scored/re-analysed job (the existing, already-established pattern - see
AnalysisRepository.save, which always inserts and lets "most recent"
define "current") rather than mutating history in place.

Usage:
    python scripts/reevaluate_recommendation_quality.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.ai.providers.factory import get_llm_provider  # noqa: E402
from app.db.models.analysis import JobAnalysisModel  # noqa: E402
from app.db.models.discovery import DiscoveredJobModel  # noqa: E402
from app.db.models.job import JobModel  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.domain.enums import DiscoveredJobStatus, JobSourceType  # noqa: E402
from app.ingestion.gmail_client import GmailClient  # noqa: E402
from app.ingestion.job_page_enrichment import enrich_posting  # noqa: E402
from app.ingestion.job_source import RawJobPosting  # noqa: E402
from app.ingestion.linkedin_email_parser import parse_linkedin_alert_email  # noqa: E402
from app.ingestion.seek_email_parser import parse_seek_alert_email  # noqa: E402
from app.repositories.ai_trace_repository import AITraceRepository  # noqa: E402
from app.repositories.analysis_repository import AnalysisRepository  # noqa: E402
from app.repositories.candidate_repository import CandidateRepository  # noqa: E402
from app.repositories.gmail_credential_repository import GmailCredentialRepository  # noqa: E402
from app.services import deduplication_service  # noqa: E402
from app.services.analysis_orchestrator import AnalysisOrchestrator  # noqa: E402
from app.services.analysis_priority_service import compute_analysis_priority  # noqa: E402
from app.services.discovery_service import DiscoveryService  # noqa: E402
from app.services.gmail_auth_service import GmailAuthService  # noqa: E402
from app.services.relevance_service import evaluate_relevance  # noqa: E402
from app.services.scoring_service import ScoringService  # noqa: E402

# The exact, known signature of the LinkedIn-login-wall enrichment bug (see
# job_page_enrichment.py) - every corrupted stored row contains this phrase
# verbatim, since it's the one unauthenticated redirect page every LinkedIn
# jobs/view/<id> URL resolves to.
CONTAMINATION_SIGNATURE = "we're signing you in"


def _is_contaminated(raw_description: str | None) -> bool:
    return CONTAMINATION_SIGNATURE in (raw_description or "").lower()


def _reparse_original_posting(
    db: Session, discovered_model: DiscoveredJobModel, gmail_client: GmailClient
) -> RawJobPosting | None:
    gmail_message_id = (discovered_model.source_metadata or {}).get("gmail_message_id")
    if not gmail_message_id:
        return None
    try:
        message = gmail_client.get_message(gmail_message_id)
    except Exception as exc:  # noqa: BLE001 - isolate one bad message
        print(f"    ! failed to fetch source message {gmail_message_id}: {exc}")
        return None
    if not message.html_body:
        return None

    if discovered_model.source == JobSourceType.LINKEDIN.value:
        postings = parse_linkedin_alert_email(
            message.html_body, message_id=gmail_message_id, received_at=message.received_at
        )
    elif discovered_model.source == JobSourceType.SEEK.value:
        postings = parse_seek_alert_email(
            message.html_body, message_id=gmail_message_id, received_at=message.received_at
        )
    else:
        return None

    for posting in postings:
        if posting.external_id == discovered_model.external_id:
            return posting
    return None


def _phase_a(db: Session, *, ai_trace_repo, spent_today: float) -> tuple[int, int, float]:
    print("=== PHASE A: re-score existing analysed jobs ===")
    orchestrator = AnalysisOrchestrator(llm_provider=get_llm_provider())
    scoring_service = ScoringService()
    analysis_repo = AnalysisRepository()
    candidate = CandidateRepository().get_singleton(db)
    assert candidate is not None

    cred = GmailCredentialRepository().get(db)
    gmail_client: GmailClient | None = None
    if cred is not None:
        auth = GmailAuthService()
        refresh_token = auth.decrypt(cred.refresh_token_encrypted)
        access_token, _ = auth.refresh_access_token(refresh_token)
        gmail_client = GmailClient(access_token=access_token)

    latest_by_job: dict[UUID, JobAnalysisModel] = {}
    for model in db.execute(select(JobAnalysisModel)).scalars():
        existing = latest_by_job.get(model.job_id)
        if existing is None or model.created_at > existing.created_at:
            latest_by_job[model.job_id] = model

    rescored = 0
    reextracted = 0
    for job_id in latest_by_job:
        job_model = db.get(JobModel, job_id)
        discovered_model = db.execute(
            select(DiscoveredJobModel).where(DiscoveredJobModel.job_id == job_id)
        ).scalar_one_or_none()
        if job_model is None or discovered_model is None:
            continue

        if _is_contaminated(job_model.raw_description) and gmail_client is not None:
            fresh = _reparse_original_posting(db, discovered_model, gmail_client)
            if fresh is not None:
                enriched = enrich_posting(fresh)
                print(f"  [reextract] {job_model.company} | {job_model.title[:50]}")
                job_model.raw_description = enriched.raw_description
                discovered_model.raw_description = enriched.raw_description
                discovered_model.description_fingerprint = (
                    deduplication_service.description_fingerprint(enriched.raw_description)
                )
                db.flush()
                try:
                    analysis = orchestrator.analyze(db, job_id)
                except Exception as exc:  # noqa: BLE001 - isolate one bad job
                    print(f"    ! re-extraction failed: {exc}")
                    continue
                reextracted += 1
                traces = ai_trace_repo.list_for_input(db, str(job_id))
                spent_today += sum(t.estimated_cost_usd or 0.0 for t in traces)
            else:
                # Couldn't recover the source message - fall back to a pure
                # deterministic re-score of the (still corrupted) stored
                # extraction, same as any other job in this phase.
                analysis = _rescore_only(db, analysis_repo, scoring_service, job_id, candidate)
        else:
            analysis = _rescore_only(db, analysis_repo, scoring_service, job_id, candidate)
            rescored += 1

        discovered_model.latest_overall_score = analysis.fit_score.overall_score
        discovered_model.latest_recommendation = analysis.fit_score.recommendation.value
        db.flush()

    db.commit()
    print(f"  Deterministically re-scored (no LLM call): {rescored}")
    print(f"  Re-extracted from source (LLM calls, contaminated only): {reextracted}")
    return rescored, reextracted, spent_today


def _rescore_only(db, analysis_repo, scoring_service, job_id, candidate):
    existing = analysis_repo.get_latest_for_job(db, job_id)
    fit_score = scoring_service.score(
        extracted_job=existing.extracted_job,
        match_result=existing.match_result,
        candidate=candidate,
    )
    return analysis_repo.save(
        db,
        job_id=job_id,
        extracted_job=existing.extracted_job,
        match_result=existing.match_result,
        fit_score=fit_score,
    )


def _phase_b(db: Session, *, app_settings, ai_trace_repo, spent_today: float) -> None:
    print("\n=== PHASE B: re-evaluate role-family-rejected jobs ===")
    candidate = CandidateRepository().get_singleton(db)
    assert candidate is not None
    service = DiscoveryService(llm_provider=get_llm_provider())

    rejected = list(
        db.execute(
            select(DiscoveredJobModel).where(
                DiscoveredJobModel.status == DiscoveredJobStatus.PREFILTER_REJECTED.value,
                DiscoveredJobModel.prefilter_reason.ilike("%no target role family%"),
            )
        )
        .scalars()
        .all()
    )
    print(f"  {len(rejected)} row(s) previously rejected for 'no target role family matched'")

    now_pass = 0
    still_rejected = 0
    promoted = 0
    analysed = 0
    analyses_this_run = 0
    max_per_run = app_settings.max_ai_analyses_per_run
    budget = app_settings.daily_ai_analysis_budget_usd

    for model in rejected:
        posting = RawJobPosting(
            title=model.title,
            company=model.company,
            location=model.location,
            source_url=model.source_url,
            source_type=JobSourceType(model.source),
            raw_description=model.raw_description,
            external_id=model.external_id,
        )
        result = evaluate_relevance(posting, candidate)
        if not result.passed:
            still_rejected += 1
            continue

        now_pass += 1
        print(f"  [now eligible] {model.company} | {model.title[:55]} -> {result.matched_family}")
        model.status = DiscoveredJobStatus.AWAITING_ANALYSIS.value
        model.prefilter_reason = None
        model.analysis_priority = compute_analysis_priority(
            posting=posting,
            search_profile=None,
            watchlist_entry=None,
            candidate_preferred_locations=candidate.preferences.preferred_locations,
        )
        db.flush()
        promoted += 1

        if analyses_this_run >= max_per_run:
            continue
        if budget is not None and spent_today >= budget:
            continue
        try:
            job, _priority = service.promote_and_analyze(db, model)
            analysed += 1
            analyses_this_run += 1
            traces = ai_trace_repo.list_for_input(db, str(job.id))
            spent_today += sum(t.estimated_cost_usd or 0.0 for t in traces)
        except Exception as exc:  # noqa: BLE001 - isolate one bad job
            print(f"    ! analysis failed: {exc}")
            model.status = DiscoveredJobStatus.ANALYSIS_FAILED.value
            db.flush()

    db.commit()
    print(f"  Now pass relevance: {now_pass}")
    print(f"  Still rejected: {still_rejected}")
    print(f"  Promoted to awaiting_analysis: {promoted}")
    print(f"  Analysed this run: {analysed}")


def main() -> int:
    db = SessionLocal()
    try:
        from app.repositories.app_settings_repository import AppSettingsRepository

        ai_trace_repo = AITraceRepository()
        app_settings = AppSettingsRepository().get(db)
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent_today = ai_trace_repo.sum_cost_since(db, today_start)
        start_spent = spent_today

        _, _, spent_today = _phase_a(db, ai_trace_repo=ai_trace_repo, spent_today=spent_today)
        _phase_b(
            db, app_settings=app_settings, ai_trace_repo=ai_trace_repo, spent_today=spent_today
        )

        end_spent = ai_trace_repo.sum_cost_since(db, today_start)
        print(f"\nIncremental AI cost this run: ${end_spent - start_spent:.4f}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
