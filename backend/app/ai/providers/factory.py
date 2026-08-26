"""Picks the active LLMProvider implementation.

This is the single place that decides *which* provider backs the app. Adding
a second real provider (e.g. OpenAI) means adding one branch here and a new
file under app/ai/providers/ - nothing else in the codebase references a
vendor SDK directly.
"""

from functools import lru_cache

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import LLMProvider
from app.ai.providers.fake_provider import FakeLLMProvider
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning(
            "no_anthropic_api_key_configured",
            note="Falling back to FakeLLMProvider - AI features will only work with canned "
            "responses. Set ANTHROPIC_API_KEY in .env to use real extraction/matching.",
        )
        return FakeLLMProvider()
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
