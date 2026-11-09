"""Application configuration via Pydantic Settings.

All values are read from environment variables or a .env file.
No defaults for secrets — they must be explicitly provided.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "FastAPI App"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ---------------------------------------------------------------------------
    # API
    # ---------------------------------------------------------------------------
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_HOSTS: list[str] = ["*"]
    CORS_ORIGINS: list[AnyHttpUrl] = []

    # ---------------------------------------------------------------------------
    # Security
    # ---------------------------------------------------------------------------
    SECRET_KEY: str                # required — no default
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # ---------------------------------------------------------------------------
    # Database
    # ---------------------------------------------------------------------------
    DATABASE_URL: PostgresDsn      # required — e.g. postgresql+asyncpg://user:pass@host/db
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False          # set True to log all SQL

    # ---------------------------------------------------------------------------
    # Redis
    # ---------------------------------------------------------------------------
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]

    # ---------------------------------------------------------------------------
    # Logging
    # ---------------------------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON: bool = True          # False → pretty-print for local dev

    # ---------------------------------------------------------------------------
    # Derived helpers
    # ---------------------------------------------------------------------------
    @field_validator("DEBUG", mode="before")
    @classmethod
    def force_debug_off_in_production(cls, v: bool, info: object) -> bool:  # noqa: ANN001
        return v

    @model_validator(mode="after")
    def production_guard(self) -> "Settings":
        if self.APP_ENV == "production" and self.DEBUG:
            raise ValueError("DEBUG must be False in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_test(self) -> bool:
        return self.APP_ENV == "test"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
