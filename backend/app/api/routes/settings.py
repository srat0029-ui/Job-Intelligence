"""Read-only, non-secret runtime configuration for the Settings page.

Deliberately exposes nothing from ANTHROPIC_API_KEY - only which model is
configured and whether a key is present at all, plus the fixed scoring
weights so the UI can show *what* drives scoring without duplicating those
constants by hand.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.scoring_service import COMPONENT_WEIGHTS

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings_info() -> dict:
    settings = get_settings()
    return {
        "environment": settings.environment,
        "anthropic_model": settings.anthropic_model,
        "anthropic_api_key_configured": bool(settings.anthropic_api_key),
        "llm_max_retries": settings.llm_max_retries,
        "scoring_weights": COMPONENT_WEIGHTS,
    }
