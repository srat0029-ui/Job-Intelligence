"""FastAPI application entrypoint."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import candidate, dashboard, health, jobs
from app.api.routes import settings as settings_routes
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Job Intelligence API",
    description="AI-powered job search command centre - backend API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(candidate.router)
app.include_router(jobs.router)
app.include_router(dashboard.router)
app.include_router(settings_routes.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Guarantees unhandled errors come back as a normal JSON response instead
    of a raw ASGI crash.

    Starlette always runs handlers registered for the bare `Exception` type
    on `ServerErrorMiddleware`, which sits OUTSIDE `CORSMiddleware` in the
    stack - so a response built here never passes back through
    CORSMiddleware and would normally have no CORS headers. The browser then
    reports the request to fetch() as an opaque "Failed to fetch" with no
    usable status/body, which is worse than not having this handler at all.
    We add the CORS header manually here for that reason.
    """
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check backend logs for details."},
    )
    origin = request.headers.get("origin")
    if origin in settings.cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
