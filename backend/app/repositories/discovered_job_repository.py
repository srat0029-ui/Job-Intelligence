"""Data access for the discovered-job landing table.

Exposes both domain-returning reads (for the API/feed) and a couple of
raw-model accessors (`get_model`) for `DiscoveryService`'s internal
read-modify-write use as a posting moves through
discovered -> [duplicate | prefilter_rejected | awaiting_analysis] ->
[analysing -> analysed | analysis_failed] - the same pattern
CandidateRepository already uses for its own orchestration-facing reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.discovery import DiscoveredJobModel
from app.domain.discovery import DiscoveredJob
from app.domain.enums import DiscoveredJobStatus, JobSourceType
from app.ingestion.job_source import RawJobPosting


def _to_domain(model: DiscoveredJobModel) -> DiscoveredJob:
    return DiscoveredJob(
        id=model.id,
        source=JobSourceType(model.source),
        external_id=model.external_id,
        source_url=model.source_url,
        title=model.title,
        company=model.company,
        raw_description=model.raw_description,
        location=model.location,
        remote_type=model.remote_type,
        salary_min=model.salary_min,
        salary_max=model.salary_max,
        currency=model.currency,
        employment_type=model.employment_type,
        published_at=model.published_at,
        retrieved_at=model.retrieved_at,
        source_metadata=dict(model.source_metadata or {}),
        dedupe_fingerprint=model.dedupe_fingerprint,
        status=DiscoveredJobStatus(model.status),
        prefilter_reason=model.prefilter_reason,
        search_profile_id=model.search_profile_id,
        discovery_run_id=model.discovery_run_id,
        job_id=model.job_id,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        times_seen=model.times_seen,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class DiscoveredJobRepository:
    def create(
        self,
        db: Session,
        *,
        posting: RawJobPosting,
        fingerprint: str,
        description_fingerprint: str,
        search_profile_id: UUID | None,
        discovery_run_id: UUID | None,
    ) -> DiscoveredJobModel:
        now = datetime.now(UTC)
        model = DiscoveredJobModel(
            source=posting.source_type.value,
            external_id=posting.external_id,
            source_url=posting.source_url,
            title=posting.title,
            company=posting.company,
            raw_description=posting.raw_description,
            location=posting.location,
            remote_type=posting.remote_type,
            salary_min=posting.salary_min,
            salary_max=posting.salary_max,
            currency=posting.currency,
            employment_type=posting.employment_type,
            published_at=posting.published_at,
            retrieved_at=posting.retrieved_at or now,
            source_metadata=dict(posting.source_metadata or {}),
            dedupe_fingerprint=fingerprint,
            description_fingerprint=description_fingerprint,
            status=DiscoveredJobStatus.DISCOVERED.value,
            search_profile_id=search_profile_id,
            discovery_run_id=discovery_run_id,
            first_seen_at=now,
            last_seen_at=now,
            times_seen=1,
        )
        db.add(model)
        db.flush()
        return model

    def mark_seen_again(self, db: Session, model: DiscoveredJobModel) -> None:
        model.last_seen_at = datetime.now(UTC)
        model.times_seen += 1
        db.flush()

    def get_model(self, db: Session, discovered_job_id: UUID) -> DiscoveredJobModel | None:
        return db.get(DiscoveredJobModel, discovered_job_id)

    def get(self, db: Session, discovered_job_id: UUID) -> DiscoveredJob | None:
        model = db.get(DiscoveredJobModel, discovered_job_id)
        return _to_domain(model) if model else None

    def get_by_job_id(self, db: Session, job_id: UUID) -> DiscoveredJob | None:
        model = db.execute(
            select(DiscoveredJobModel).where(DiscoveredJobModel.job_id == job_id)
        ).scalar_one_or_none()
        return _to_domain(model) if model else None

    def list_all(self, db: Session) -> list[DiscoveredJob]:
        models = (
            db.execute(select(DiscoveredJobModel).order_by(DiscoveredJobModel.created_at.desc()))
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def list_awaiting_analysis(
        self, db: Session, discovery_run_id: UUID | None = None
    ) -> list[DiscoveredJobModel]:
        stmt = select(DiscoveredJobModel).where(
            DiscoveredJobModel.status == DiscoveredJobStatus.AWAITING_ANALYSIS.value
        )
        if discovery_run_id is not None:
            stmt = stmt.where(DiscoveredJobModel.discovery_run_id == discovery_run_id)
        return list(db.execute(stmt).scalars().all())
