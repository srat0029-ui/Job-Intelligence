"""Dashboard aggregate endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_dashboard_service, get_db
from app.api.schemas import DashboardStats, JobListItem
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
def get_dashboard(
    db: Session = Depends(get_db), service: DashboardService = Depends(get_dashboard_service)
) -> DashboardStats:
    return service.get_stats(db)


@router.get("/prioritized", response_model=list[JobListItem])
def get_prioritized_jobs(
    db: Session = Depends(get_db), service: DashboardService = Depends(get_dashboard_service)
) -> list[JobListItem]:
    """All jobs ranked by latest fit score - backs the Analysis page."""
    return service.list_prioritized(db)
