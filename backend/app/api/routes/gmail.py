"""Gmail OAuth connection endpoints - SEEK/LinkedIn job-alert ingestion.

Read-only (`gmail.readonly` scope only, requested in
GmailAuthService.build_authorize_url). Nothing here ever returns a token to
the frontend - `GmailStatus` only ever carries connected/email/sync
metadata (see gmail_service.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.services.gmail_auth_service import TokenExchangeError
from app.services.gmail_service import GmailService, GmailStatus

router = APIRouter(prefix="/api/gmail", tags=["gmail"])


def get_gmail_service() -> GmailService:
    return GmailService()


@router.get("/connect")
def connect(service: GmailService = Depends(get_gmail_service)) -> RedirectResponse:
    try:
        url = service.build_connect_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url)


@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    service: GmailService = Depends(get_gmail_service),
) -> RedirectResponse:
    frontend_settings_url = f"{get_settings().cors_origins[0]}/settings"
    if error or not code:
        return RedirectResponse(f"{frontend_settings_url}?gmail_error={error or 'no_code'}")
    try:
        service.handle_callback(db, code=code)
    except TokenExchangeError as exc:
        return RedirectResponse(f"{frontend_settings_url}?gmail_error={exc}")
    return RedirectResponse(f"{frontend_settings_url}?gmail_connected=1")


@router.get("/status", response_model=GmailStatus)
def status(
    db: Session = Depends(get_db), service: GmailService = Depends(get_gmail_service)
) -> GmailStatus:
    return service.get_status(db)


@router.post("/disconnect")
def disconnect(
    db: Session = Depends(get_db), service: GmailService = Depends(get_gmail_service)
) -> dict[str, bool]:
    return {"disconnected": service.disconnect(db)}
