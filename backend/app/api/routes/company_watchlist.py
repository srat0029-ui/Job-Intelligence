"""Target-company watchlist endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_company_watchlist_service, get_db
from app.domain.company_watchlist import CompanyWatchlistEntry
from app.services.company_watchlist_service import CompanyWatchlistService

router = APIRouter(prefix="/api/company-watchlist", tags=["company-watchlist"])


@router.get("", response_model=list[CompanyWatchlistEntry])
def list_watchlist(
    db: Session = Depends(get_db),
    service: CompanyWatchlistService = Depends(get_company_watchlist_service),
) -> list[CompanyWatchlistEntry]:
    return service.list_all(db)


@router.post("", response_model=CompanyWatchlistEntry, status_code=201)
def create_watchlist_entry(
    entry: CompanyWatchlistEntry,
    db: Session = Depends(get_db),
    service: CompanyWatchlistService = Depends(get_company_watchlist_service),
) -> CompanyWatchlistEntry:
    if not entry.company_name.strip() or not entry.ats_identifier.strip():
        raise HTTPException(status_code=422, detail="Company name and ATS identifier are required.")
    return service.create(db, entry)


@router.put("/{entry_id}", response_model=CompanyWatchlistEntry)
def update_watchlist_entry(
    entry_id: UUID,
    entry: CompanyWatchlistEntry,
    db: Session = Depends(get_db),
    service: CompanyWatchlistService = Depends(get_company_watchlist_service),
) -> CompanyWatchlistEntry:
    updated = service.update(db, entry_id, entry)
    if updated is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return updated


@router.delete("/{entry_id}", status_code=204)
def delete_watchlist_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    service: CompanyWatchlistService = Depends(get_company_watchlist_service),
) -> None:
    if not service.delete(db, entry_id):
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
