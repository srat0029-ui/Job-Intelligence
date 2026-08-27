"""Dev-only follow-up to reevaluate_recommendation_quality.py.

That script fixed the login-wall contamination bug and found a second,
narrower one behind it: even with a clean alert-email snippet, most real
LinkedIn/SEEK job-alert listings carry almost no body description at all
(just title + company + location, occasionally a salary line) - so
extraction was still finding zero requirements for most jobs, just for a
different reason. Two changes since address this:

1. app/ingestion/linkedin_email_parser.py: the alumni-badge regex didn't
   match LinkedIn's real singular phrasing ("1 school alum", not "1 school
   alumni"), so it was leaking into `raw_description` as if it were content
   for jobs with that exact badge.
2. app/ai/prompts/extraction_v1.py: the extraction prompt now explicitly
   tells the model the title itself is fair game for requirements/
   seniority (many titles carry real signal - "(C#/.NET)", "Business AI
   Architect" - that a near-empty body description can't offer), instead of
   only working from `raw_description`. Verified against real IBM/Recoded/
   SAP titles before this script was written: seniority and technology
   requirements are now extracted where they previously came back empty.

This re-runs extraction+matching+scoring (new LLM calls - see the module's
sibling script for why this is a necessary case, not an "unnecessary" one:
purely deterministic re-scoring of a genuinely empty extraction can't
differentiate anything) for every analysed job whose latest extraction
still has zero requirements. For LinkedIn-sourced jobs, also re-fetches and
re-parses the original Gmail message first (picks up the alumni-regex fix).

Usage:
    python scripts/rerun_thin_extractions.py
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
from app.domain.enums import JobSourceType  # noqa: E402
from app.ingestion.gmail_client import GmailClient  # noqa: E402
from app.ingestion.job_page_enrichment import enrich_posting  # noqa: E402
from app.ingestion.linkedin_email_parser import parse_linkedin_alert_email  # noqa: E402
from app.repositories.ai_trace_repository import AITraceRepository  # noqa: E402
from app.repositories.candidate_repository import CandidateRepository  # noqa: E402
from app.repositories.gmail_credential_repository import GmailCredentialRepository  # noqa: E402
from app.services import deduplication_service  # noqa: E402
from app.services.analysis_orchestrator import AnalysisOrchestrator  # noqa: E402
from app.services.gmail_auth_service import GmailAuthService  # noqa: E402


def main() -> int:
    db: Session = SessionLocal()
    try:
        candidate = CandidateRepository().get_singleton(db)
        assert candidate is not None
        orchestrator = AnalysisOrchestrator(llm_provider=get_llm_provider())
        ai_trace_repo = AITraceRepository()

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

        thin_job_ids = [
            job_id
            for job_id, m in latest_by_job.items()
            if len(m.extracted_job.get("requirements", [])) == 0
        ]
        print(f"{len(thin_job_ids)} analysed job(s) with zero extracted requirements")

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start_spent = ai_trace_repo.sum_cost_since(db, today_start)

        reextracted = 0
        for job_id in thin_job_ids:
            job_model = db.get(JobModel, job_id)
            discovered_model = db.execute(
                select(DiscoveredJobModel).where(DiscoveredJobModel.job_id == job_id)
            ).scalar_one_or_none()
            if job_model is None or discovered_model is None:
                continue

            if job_model.source_type == JobSourceType.LINKEDIN.value and gmail_client is not None:
                gmail_message_id = (discovered_model.source_metadata or {}).get(
                    "gmail_message_id"
                )
                if gmail_message_id:
                    try:
                        message = gmail_client.get_message(gmail_message_id)
                    except Exception as exc:  # noqa: BLE001 - isolate one bad message
                        print(f"  ! failed to fetch {gmail_message_id}: {exc}")
                        message = None
                    if message is not None and message.html_body:
                        fresh = next(
                            (
                                p
                                for p in parse_linkedin_alert_email(
                                    message.html_body,
                                    message_id=gmail_message_id,
                                    received_at=message.received_at,
                                )
                                if p.external_id == discovered_model.external_id
                            ),
                            None,
                        )
                        if fresh is not None:
                            enriched = enrich_posting(fresh)
                            job_model.raw_description = enriched.raw_description
                            discovered_model.raw_description = enriched.raw_description
                            discovered_model.description_fingerprint = (
                                deduplication_service.description_fingerprint(
                                    enriched.raw_description
                                )
                            )
                            db.flush()

            print(f"  [reextract] {job_model.company} | {job_model.title[:50]}")
            try:
                analysis = orchestrator.analyze(db, job_id)
            except Exception as exc:  # noqa: BLE001 - isolate one bad job
                print(f"    ! failed: {exc}")
                continue
            reextracted += 1
            discovered_model.latest_overall_score = analysis.fit_score.overall_score
            discovered_model.latest_recommendation = analysis.fit_score.recommendation.value
            db.flush()

        db.commit()
        end_spent = ai_trace_repo.sum_cost_since(db, today_start)
        print(f"\nRe-extracted: {reextracted}")
        print(f"Incremental AI cost this run: ${end_spent - start_spent:.4f}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
