"""Application settings loaded from environment variables (12-factor style).

Secrets are never given real defaults. Production-unsafe combinations are
rejected at start-up so a misconfigured deployment fails loudly instead of
running with weak security.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EXL Personalized Financial Advisor API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # Database: SQLite file for zero-dependency local demos; PostgreSQL (Supabase) otherwise.
    database_url: str = "sqlite:///./data/local.db"
    database_echo: bool = False

    # Authentication
    auth_mode: Literal["local", "supabase"] = "local"
    local_jwt_secret: SecretStr | None = None
    local_demo_password: SecretStr | None = None
    local_token_ttl_minutes: int = Field(default=480, ge=5, le=1440)
    supabase_url: str | None = None
    supabase_jwt_secret: SecretStr | None = None  # only for projects still on legacy HS256 signing
    supabase_jwt_audience: str = "authenticated"

    # HTTP hardening
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    request_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    max_request_body_bytes: int = Field(default=65_536, ge=1_024)
    rate_limit_sensitive_per_minute: int = Field(default=20, ge=1)
    rate_limit_login_per_minute: int = Field(default=5, ge=1)
    default_page_size: int = Field(default=50, ge=1, le=200)
    max_page_size: int = Field(default=200, ge=1, le=1000)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def supabase_jwks_url(self) -> str | None:
        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str | None:
        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @model_validator(mode="after")
    def _validate_security(self) -> Settings:
        if "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins; '*' is not allowed")
        if self.auth_mode == "local":
            secret = self.local_jwt_secret.get_secret_value() if self.local_jwt_secret else ""
            if len(secret) < 32:
                raise ValueError("LOCAL_JWT_SECRET must be set to at least 32 characters when AUTH_MODE=local")
            if not self.local_demo_password or len(self.local_demo_password.get_secret_value()) < 8:
                raise ValueError("LOCAL_DEMO_PASSWORD must be set (8+ characters) when AUTH_MODE=local")
        if self.auth_mode == "supabase" and not self.supabase_url:
            raise ValueError("SUPABASE_URL is required when AUTH_MODE=supabase")
        if self.environment == "production":
            if self.auth_mode != "supabase":
                raise ValueError("Production requires AUTH_MODE=supabase (local demo auth is development-only)")
            if self.is_sqlite:
                raise ValueError("Production requires a PostgreSQL DATABASE_URL")
            if any(o.startswith("http://") and "localhost" not in o for o in self.cors_allowed_origins):
                raise ValueError("Production CORS origins must use https")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
