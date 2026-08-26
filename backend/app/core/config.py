"""Application configuration loaded from environment variables.

Centralising config here means secrets (API keys, DB credentials) are read
once, validated, and never touched directly by services or routes.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://job_intel:job_intel@localhost:5432/job_intelligence",
        description="SQLAlchemy connection string (psycopg3 driver).",
    )

    # AI provider
    anthropic_api_key: str = Field(
        default="", description="Server-side only. Never exposed to frontend."
    )
    anthropic_model: str = Field(default="claude-sonnet-5")
    llm_max_retries: int = Field(default=2)
    llm_timeout_seconds: float = Field(default=60.0, description="Bounds tail latency per attempt.")

    # App
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Estimated pricing (USD per 1M tokens) used only for cost logging/estimates.
    llm_input_cost_per_million: float = Field(default=3.0)
    llm_output_cost_per_million: float = Field(default=15.0)

    # Adzuna (job discovery source) - server-side only, never exposed to frontend.
    adzuna_app_id: str = Field(default="")
    adzuna_app_key: str = Field(default="")
    adzuna_country: str = Field(default="au")


@lru_cache
def get_settings() -> Settings:
    return Settings()
