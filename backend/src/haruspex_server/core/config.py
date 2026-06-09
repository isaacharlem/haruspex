"""Application configuration. Every variable is documented in .env.example."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HARUSPEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://haruspex:haruspex@localhost:55432/haruspex"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    log_level: str = "info"
    worker_interval_s: float = 15.0
    heartbeat_stale_s: float = 120.0
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    copilot_model: str = "claude-sonnet-4-6"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def asyncpg_dsn(self) -> str:
        """Plain libpq-style DSN for the raw asyncpg LISTEN connection."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
