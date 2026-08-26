"""Data access for the discovered-job landing table.

Exposes both domain-returning reads (for the API/feed) and a couple of
raw-model accessors (`get_model`) for `DiscoveryService`'s internal
read-modify-write use as a posting moves through
discovered -> [duplicate | prefilter_rejected | awaiting_analysis] ->
[analysing -> analysed | analysis_failed] - the same pattern
CandidateRepository already uses for its own orchestration-facing reads.

`list_paginated` is the one method the opportunity feed actually calls -
filtering/sorting/pagination all happen in SQL (WHERE/ORDER BY/LIMIT/
OFFSET), not by loading every row into Python. This relies on
`latest_overall_score`/`latest_recommendation`/`latest_priority` being kept
denormalised on the row itself (updated right after analysis - see
DiscoveryService), so the feed query never needs to join job_analyses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models.discovery import DiscoveredJobModel, SourceObservationModel
from app.domain.discovery import DiscoveredJob, SourceObservation
from app.domain.enums import (
    DiscoveredJobStatus,
    DuplicateMatchStage,
    GeographicEligibility,
    JobPriority,
    JobSourceType,
)
from app.ingestion.job_source import RawJobPosting

SORT_COLUMNS = {
    "score": DiscoveredJobModel.latest_overall_score,
    "posted_date": DiscoveredJobModel.published_at,
    "discovered_date": DiscoveredJobModel.created_at,
    "company": DiscoveredJobModel.company,
    "title": DiscoveredJobModel.title,
    "location": DiscoveredJobModel.location,
    "analysis_priority": DiscoveredJobModel.analysis_priority,
}


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
        country=model.country,
        geographic_eligibility=GeographicEligibility(model.geographic_eligibility),
        geographic_eligibility_reason=model.geographic_eligibility_reason,
        search_profile_id=model.search_profile_id,
        discovery_run_id=model.discovery_run_id,
        job_id=model.job_id,
        analysis_priority=model.analysis_priority,
        latest_overall_score=model.latest_overall_score,
        latest_recommendation=model.latest_recommendation,
        latest_priority=model.latest_priority,
        reviewed_at=model.reviewed_at,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        times_seen=model.times_seen,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _observation_to_domain(model: SourceObservationModel) -> SourceObservation:
    return SourceObservation(
        id=model.id,
        discovered_job_id=model.discovered_job_id,
        source=JobSourceType(model.source),
        external_id=model.external_id,
        source_url=model.source_url,
        match_stage=DuplicateMatchStage(model.match_stage),
        match_confidence=model.match_confidence,
        match_reason=model.match_reason,
        discovery_run_id=model.discovery_run_id,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        times_seen=model.times_seen,
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
        country: str | None = None,
        geographic_eligibility: GeographicEligibility = GeographicEligibility.LOCATION_UNCONFIRMED,
        geographic_eligibility_reason: str | None = None,
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
            country=country,
            geographic_eligibility=geographic_eligibility.value,
            geographic_eligibility_reason=geographic_eligibility_reason,
            search_profile_id=search_profile_id,
            discovery_run_id=discovery_run_id,
            first_seen_at=now,
            last_seen_at=now,
            times_seen=1,
        )
        db.add(model)
        db.flush()

        db.add(
            SourceObservationModel(
                discovered_job_id=model.id,
                source=posting.source_type.value,
                external_id=posting.external_id,
                source_url=posting.source_url,
                match_stage=DuplicateMatchStage.ORIGINAL.value,
                match_confidence=1.0,
                match_reason=None,
                discovery_run_id=discovery_run_id,
                first_seen_at=now,
                last_seen_at=now,
                times_seen=1,
            )
        )
        db.flush()
        return model

    def add_observation(
        self,
        db: Session,
        *,
        discovered_job_id: UUID,
        posting: RawJobPosting,
        stage: DuplicateMatchStage,
        confidence: float,
        reason: str | None,
        discovery_run_id: UUID | None,
    ) -> SourceObservationModel:
        """Records one more sighting of an existing canonical job. If this
        exact (source, external_id) was already observed, bumps its
        last_seen_at/times_seen instead of creating a second row for it."""
        existing = None
        if posting.external_id:
            existing = (
                db.execute(
                    select(SourceObservationModel).where(
                        SourceObservationModel.discovered_job_id == discovered_job_id,
                        SourceObservationModel.source == posting.source_type.value,
                        SourceObservationModel.external_id == posting.external_id,
                    )
                )
                .scalars()
                .first()
            )
        now = datetime.now(UTC)
        if existing is not None:
            existing.last_seen_at = now
            existing.times_seen += 1
            db.flush()
            return existing

        observation = SourceObservationModel(
            discovered_job_id=discovered_job_id,
            source=posting.source_type.value,
            external_id=posting.external_id,
            source_url=posting.source_url,
            match_stage=stage.value,
            match_confidence=confidence,
            match_reason=reason,
            discovery_run_id=discovery_run_id,
            first_seen_at=now,
            last_seen_at=now,
            times_seen=1,
        )
        db.add(observation)
        db.flush()
        return observation

    def list_observations(self, db: Session, discovered_job_id: UUID) -> list[SourceObservation]:
        models = (
            db.execute(
                select(SourceObservationModel)
                .where(SourceObservationModel.discovered_job_id == discovered_job_id)
                .order_by(SourceObservationModel.first_seen_at.asc())
            )
            .scalars()
            .all()
        )
        return [_observation_to_domain(m) for m in models]

    def mark_seen_again(self, db: Session, model: DiscoveredJobModel) -> None:
        model.last_seen_at = datetime.now(UTC)
        model.times_seen += 1
        db.flush()

    def mark_reviewed(self, db: Session, discovered_job_id: UUID) -> DiscoveredJob | None:
        model = db.get(DiscoveredJobModel, discovered_job_id)
        if model is None:
            return None
        model.reviewed_at = datetime.now(UTC)
        db.commit()
        db.refresh(model)
        return _to_domain(model)

    def archive(self, db: Session, discovered_job_id: UUID) -> DiscoveredJob | None:
        """"Ignore" for a not-yet-promoted discovered job - reuses the
        existing ARCHIVED status rather than adding a parallel concept."""
        model = db.get(DiscoveredJobModel, discovered_job_id)
        if model is None:
            return None
        model.status = DiscoveredJobStatus.ARCHIVED.value
        db.commit()
        db.refresh(model)
        return _to_domain(model)

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

    def list_all_models(self, db: Session) -> list[DiscoveredJobModel]:
        """Raw ORM rows, for the location-eligibility backfill script -
        never used by request-serving code paths."""
        return list(
            db.execute(
                select(DiscoveredJobModel).order_by(DiscoveredJobModel.created_at.asc())
            ).scalars()
        )

    def set_geographic_eligibility(
        self,
        db: Session,
        discovered_job_id: UUID,
        *,
        country: str | None,
        geographic_eligibility: GeographicEligibility,
        geographic_eligibility_reason: str | None,
        reclassify_status_if_ineligible: bool = True,
    ) -> None:
        model = db.get(DiscoveredJobModel, discovered_job_id)
        if model is None:
            return
        model.country = country
        model.geographic_eligibility = geographic_eligibility.value
        model.geographic_eligibility_reason = geographic_eligibility_reason
        reclassifiable_statuses = (
            DiscoveredJobStatus.DISCOVERED.value,
            DiscoveredJobStatus.AWAITING_ANALYSIS.value,
        )
        if (
            reclassify_status_if_ineligible
            and geographic_eligibility != GeographicEligibility.ELIGIBLE
            and model.status in reclassifiable_statuses
        ):
            model.status = DiscoveredJobStatus.PREFILTER_REJECTED.value
            model.prefilter_reason = geographic_eligibility_reason
        db.flush()

    def list_by_run(self, db: Session, discovery_run_id: UUID) -> list[DiscoveredJob]:
        models = (
            db.execute(
                select(DiscoveredJobModel)
                .where(DiscoveredJobModel.discovery_run_id == discovery_run_id)
                .order_by(DiscoveredJobModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(m) for m in models]

    def count_created_since(self, db: Session, since: datetime) -> int:
        """Counts only geographically-eligible postings - "new jobs today"
        on the home feed should never include jobs that were always going
        to be hidden."""
        return db.execute(
            select(func.count()).where(
                DiscoveredJobModel.created_at >= since,
                DiscoveredJobModel.geographic_eligibility == GeographicEligibility.ELIGIBLE.value,
            )
        ).scalar_one()

    def count_high_priority_unreviewed(self, db: Session) -> int:
        return db.execute(
            select(func.count()).where(
                DiscoveredJobModel.latest_priority.in_(
                    [JobPriority.APPLY_ASAP.value, JobPriority.STRONG_APPLY.value]
                ),
                DiscoveredJobModel.reviewed_at.is_(None),
                DiscoveredJobModel.geographic_eligibility == GeographicEligibility.ELIGIBLE.value,
            )
        ).scalar_one()

    def list_awaiting_analysis(
        self, db: Session, discovery_run_id: UUID | None = None
    ) -> list[DiscoveredJobModel]:
        """Ordered by analysis_priority DESC (nulls last) - the deterministic
        pre-LLM triage order the analysis phase spends its budget in."""
        stmt = select(DiscoveredJobModel).where(
            DiscoveredJobModel.status == DiscoveredJobStatus.AWAITING_ANALYSIS.value
        )
        if discovery_run_id is not None:
            stmt = stmt.where(DiscoveredJobModel.discovery_run_id == discovery_run_id)
        stmt = stmt.order_by(DiscoveredJobModel.analysis_priority.desc().nullslast())
        return list(db.execute(stmt).scalars().all())

    def _apply_filters(
        self,
        stmt: Select,
        *,
        status: DiscoveredJobStatus | None,
        exclude_statuses: list[DiscoveredJobStatus] | None,
        search_profile_id: UUID | None,
        min_score: float | None,
        analysed_only: bool,
        reviewed: bool | None,
        require_eligible_location: bool = True,
    ) -> Select:
        if status is not None:
            stmt = stmt.where(DiscoveredJobModel.status == status.value)
        elif exclude_statuses:
            stmt = stmt.where(
                DiscoveredJobModel.status.not_in([s.value for s in exclude_statuses])
            )
        if search_profile_id is not None:
            stmt = stmt.where(DiscoveredJobModel.search_profile_id == search_profile_id)
        if min_score is not None:
            stmt = stmt.where(DiscoveredJobModel.latest_overall_score >= min_score)
        if analysed_only:
            stmt = stmt.where(DiscoveredJobModel.latest_overall_score.is_not(None))
        if reviewed is True:
            stmt = stmt.where(DiscoveredJobModel.reviewed_at.is_not(None))
        elif reviewed is False:
            stmt = stmt.where(DiscoveredJobModel.reviewed_at.is_(None))
        if require_eligible_location:
            # The hard, deterministic Australia-eligibility gate - never a
            # scoring preference. INELIGIBLE and LOCATION_UNCONFIRMED are
            # both hidden from the recommended feed by default; pass
            # require_eligible_location=False (Advanced/debug views only)
            # to see everything, e.g. for auditing why a job was excluded.
            stmt = stmt.where(
                DiscoveredJobModel.geographic_eligibility == GeographicEligibility.ELIGIBLE.value
            )
        return stmt

    def list_paginated(
        self,
        db: Session,
        *,
        status: DiscoveredJobStatus | None = None,
        exclude_statuses: list[DiscoveredJobStatus] | None = None,
        search_profile_id: UUID | None = None,
        min_score: float | None = None,
        analysed_only: bool = False,
        reviewed: bool | None = None,
        require_eligible_location: bool = True,
        sort_by: str = "score",
        descending: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DiscoveredJob], int]:
        base = select(DiscoveredJobModel)
        base = self._apply_filters(
            base,
            status=status,
            exclude_statuses=exclude_statuses,
            search_profile_id=search_profile_id,
            min_score=min_score,
            analysed_only=analysed_only,
            reviewed=reviewed,
            require_eligible_location=require_eligible_location,
        )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = db.execute(count_stmt).scalar_one()

        column = SORT_COLUMNS.get(sort_by, DiscoveredJobModel.latest_overall_score)
        order = column.desc().nullslast() if descending else column.asc().nullsfirst()
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        stmt = base.order_by(order).limit(page_size).offset((page - 1) * page_size)

        models = db.execute(stmt).scalars().all()
        return [_to_domain(m) for m in models], total
