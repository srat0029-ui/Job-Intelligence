"""Discovery endpoints: search profiles, running discovery, the ranked
opportunity feed, discovery-run history/detail, and cost/AI-analysis
controls."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    get_app_settings_service,
    get_db,
    get_discovery_service,
    get_opportunity_service,
    get_search_profile_service,
)
from app.api.schemas import CostSummary, RunDiscoveryRequest
from app.domain.app_settings import AppSettings
from app.domain.discovery import DiscoveredJob, DiscoveryRun, SearchProfile
from app.domain.enums import DiscoveredJobStatus
from app.repositories.ai_trace_repository import AITraceRepository
from app.repositories.discovered_job_repository import DiscoveredJobRepository
from app.repositories.discovery_run_repository import DiscoveryRunRepository
from app.services.analysis_orchestrator import CandidateProfileMissingError
from app.services.app_settings_service import AppSettingsService
from app.services.discovery_service import (
    DiscoveryAlreadyRunningError,
    DiscoveryService,
    NoSearchProfilesError,
)
from app.services.opportunity_service import OpportunityItem, OpportunityPage, OpportunityService
from app.services.search_profile_service import SearchProfileService

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


# --- Search profiles ---


@router.get("/search-profiles", response_model=list[SearchProfile])
def list_search_profiles(
    db: Session = Depends(get_db),
    service: SearchProfileService = Depends(get_search_profile_service),
) -> list[SearchProfile]:
    return service.list_all(db)


@router.post("/search-profiles", response_model=SearchProfile, status_code=201)
def create_search_profile(
    profile: SearchProfile,
    db: Session = Depends(get_db),
    service: SearchProfileService = Depends(get_search_profile_service),
) -> SearchProfile:
    if not profile.name.strip():
        raise HTTPException(status_code=422, detail="Search profile name is required.")
    return service.create(db, profile)


@router.put("/search-profiles/{profile_id}", response_model=SearchProfile)
def update_search_profile(
    profile_id: UUID,
    profile: SearchProfile,
    db: Session = Depends(get_db),
    service: SearchProfileService = Depends(get_search_profile_service),
) -> SearchProfile:
    updated = service.update(db, profile_id, profile)
    if updated is None:
        raise HTTPException(status_code=404, detail="Search profile not found")
    return updated


@router.delete("/search-profiles/{profile_id}", status_code=204)
def delete_search_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    service: SearchProfileService = Depends(get_search_profile_service),
) -> None:
    if not service.delete(db, profile_id):
        raise HTTPException(status_code=404, detail="Search profile not found")


# --- Running discovery ---


@router.post("/run", response_model=DiscoveryRun)
def run_discovery(
    payload: RunDiscoveryRequest,
    db: Session = Depends(get_db),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryRun:
    try:
        return service.run(db, search_profile_ids=payload.search_profile_ids, triggered_by="manual")
    except CandidateProfileMissingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoSearchProfilesError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DiscoveryAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs", response_model=list[DiscoveryRun])
def list_discovery_runs(db: Session = Depends(get_db)) -> list[DiscoveryRun]:
    return DiscoveryRunRepository().list_recent(db)


@router.get("/runs/{run_id}", response_model=DiscoveryRun)
def get_discovery_run(run_id: UUID, db: Session = Depends(get_db)) -> DiscoveryRun:
    run = DiscoveryRunRepository().get(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return run


@router.get("/runs/{run_id}/jobs", response_model=list[DiscoveredJob])
def get_discovery_run_jobs(run_id: UUID, db: Session = Depends(get_db)) -> list[DiscoveredJob]:
    """Per-job breakdown for one run - for development/debugging "why was
    this job filtered/deduplicated/deferred". Includes each job's status,
    prefilter_reason, and analysis_priority as first discovered in this run
    (a job later found to be a duplicate of an earlier run's canonical
    record won't appear here as a *new* row - see its source observations
    instead via the canonical job)."""
    return DiscoveredJobRepository().list_by_run(db, run_id)


# --- Opportunity feed ---


@router.get("/opportunities", response_model=OpportunityPage)
def list_opportunities(
    db: Session = Depends(get_db),
    service: OpportunityService = Depends(get_opportunity_service),
    sort_by: str = Query(default="score"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status: DiscoveredJobStatus | None = Query(default=None),
    search_profile_id: UUID | None = Query(default=None),
    include_rejected: bool = Query(default=False),
    analysed_only: bool = Query(default=False),
    reviewed: bool | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> OpportunityPage:
    return service.list_opportunities(
        db,
        sort_by=sort_by,
        descending=(order == "desc"),
        status=status,
        search_profile_id=search_profile_id,
        include_rejected=include_rejected,
        analysed_only=analysed_only,
        reviewed=reviewed,
        min_score=min_score,
        page=page,
        page_size=page_size,
    )


@router.put("/opportunities/{discovered_job_id}/reviewed", response_model=DiscoveredJob)
def mark_opportunity_reviewed(
    discovered_job_id: UUID,
    db: Session = Depends(get_db),
    service: OpportunityService = Depends(get_opportunity_service),
) -> DiscoveredJob:
    item = service.mark_reviewed(db, discovered_job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Discovered job not found")
    return item


@router.put("/opportunities/{discovered_job_id}/ignore", response_model=DiscoveredJob)
def ignore_opportunity(
    discovered_job_id: UUID,
    db: Session = Depends(get_db),
    service: OpportunityService = Depends(get_opportunity_service),
) -> DiscoveredJob:
    item = service.ignore(db, discovered_job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Discovered job not found")
    return item


@router.post("/discovered-jobs/{discovered_job_id}/analyze", response_model=OpportunityItem)
def force_analyze_discovered_job(
    discovered_job_id: UUID,
    db: Session = Depends(get_db),
    discovery_service: DiscoveryService = Depends(get_discovery_service),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityItem:
    """Manual override: analyse one discovered job right now regardless of
    the auto-analysis toggle, per-run limit, or daily budget - those only
    govern the automated phase of a discovery run. Reuses
    DiscoveryService.promote_and_analyze so there is exactly one code path
    that turns a DiscoveredJob into an analysed Job."""
    discovered_repo = DiscoveredJobRepository()
    model = discovered_repo.get_model(db, discovered_job_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Discovered job not found")

    try:
        discovery_service.promote_and_analyze(db, model)
    except CandidateProfileMissingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Look the specific job up directly by filtering to just its status
    # rather than trusting where it'd land in a large, sorted page.
    page = opportunity_service.list_opportunities(
        db, include_rejected=True, sort_by="discovered_date", page_size=200
    )
    item = next((i for i in page.items if i.discovered_job_id == discovered_job_id), None)
    if item is None:
        raise HTTPException(status_code=500, detail="Analysis succeeded but item lookup failed")
    return item


# --- App settings / cost controls ---


@router.get("/settings", response_model=AppSettings)
def get_discovery_settings(
    db: Session = Depends(get_db), service: AppSettingsService = Depends(get_app_settings_service)
) -> AppSettings:
    return service.get(db)


@router.put("/settings", response_model=AppSettings)
def update_discovery_settings(
    settings: AppSettings,
    db: Session = Depends(get_db),
    service: AppSettingsService = Depends(get_app_settings_service),
) -> AppSettings:
    return service.update(db, settings)


@router.get("/cost-summary", response_model=CostSummary)
def get_cost_summary(
    db: Session = Depends(get_db), service: AppSettingsService = Depends(get_app_settings_service)
) -> CostSummary:
    trace_repo = AITraceRepository()
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    settings = service.get(db)
    return CostSummary(
        spent_today_usd=trace_repo.sum_cost_since(db, today_start),
        spent_all_time_usd=trace_repo.sum_cost_all_time(db),
        daily_budget_usd=settings.daily_ai_analysis_budget_usd,
    )
