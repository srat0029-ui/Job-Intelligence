"""Liveness endpoint - deliberately has no DB/LLM dependency so it can be
used as a container healthcheck even if the DB is briefly unreachable."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
