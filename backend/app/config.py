"""Application settings, loaded from environment variables.

Every variable is documented in the repository's `.env.example`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_name: str = "JobPilot"
    environment: str = Field(default="production", alias="JOBPILOT_ENV")
    secret_key: str = Field(default="change-me-in-.env", alias="SECRET_KEY")
    port: int = Field(default=1456, alias="PORT")
    public_url: str | None = Field(default=None, alias="PUBLIC_URL")

    # Storage
    database_url: str = Field(
        default="postgresql+psycopg://jobpilot:jobpilot@db:5432/jobpilot", alias="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    upload_dir: Path = Field(default=Path("/data/uploads"), alias="UPLOAD_DIR")
    max_upload_mb: int = Field(default=15, alias="MAX_UPLOAD_MB")

    # LLM
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="claude-opus-5", alias="LLM_MODEL")
    llm_dry_run: bool = Field(default=False, alias="LLM_DRY_RUN")

    # Discovery: optional aggregator / search keys. Absent keys disable the
    # source gracefully — nothing falls back to scraping.
    adzuna_app_id: str | None = Field(default=None, alias="ADZUNA_APP_ID")
    adzuna_app_key: str | None = Field(default=None, alias="ADZUNA_APP_KEY")
    jooble_api_key: str | None = Field(default=None, alias="JOOBLE_API_KEY")
    usajobs_api_key: str | None = Field(default=None, alias="USAJOBS_API_KEY")
    usajobs_user_agent_email: str | None = Field(default=None, alias="USAJOBS_EMAIL")
    themuse_api_key: str | None = Field(default=None, alias="THEMUSE_API_KEY")
    brave_search_api_key: str | None = Field(default=None, alias="BRAVE_SEARCH_API_KEY")
    serpapi_api_key: str | None = Field(default=None, alias="SERPAPI_API_KEY")

    # Politeness. The per-host interval can only be raised, never lowered
    # below 1 request/second — enforced in `validate_politeness`.
    min_host_interval_seconds: float = Field(default=1.0, alias="MIN_HOST_INTERVAL_SECONDS")
    source_cache_ttl_seconds: int = Field(default=1800, alias="SOURCE_CACHE_TTL_SECONDS")
    user_agent_extra: str | None = Field(default=None, alias="USER_AGENT_EXTRA")

    # Application throughput ceilings, enforced server-side in the queue
    # runner. Defaults per spec; configurable, but they remain hard caps.
    max_applications_per_hour: int = Field(default=15, alias="MAX_APPLICATIONS_PER_HOUR")
    max_applications_per_day: int = Field(default=50, alias="MAX_APPLICATIONS_PER_DAY")

    # Human-in-the-loop
    intervention_wait_minutes: int = Field(default=30, alias="INTERVENTION_WAIT_MINUTES")

    # Resolver
    resolver_confidence_threshold: float = Field(default=0.75, alias="RESOLVER_CONFIDENCE_THRESHOLD")
    freetext_trivial_length: int = Field(default=120, alias="FREETEXT_TRIVIAL_LENGTH")

    # Email notifications (optional)
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")

    # Executor
    playwright_headful: bool = Field(default=True, alias="PLAYWRIGHT_HEADFUL")
    playwright_chromium_path: str | None = Field(default=None, alias="PLAYWRIGHT_CHROMIUM_PATH")
    novnc_url: str | None = Field(default=None, alias="NOVNC_URL")

    # Session / security
    session_ttl_days: int = Field(default=30, alias="SESSION_TTL_DAYS")
    secure_cookies: bool = Field(default=False, alias="SECURE_COOKIES")

    @property
    def is_public(self) -> bool:
        return bool(self.public_url)

    @property
    def cookies_secure(self) -> bool:
        # When exposed beyond localhost the UI must run behind HTTPS.
        return self.secure_cookies or (
            self.public_url is not None and self.public_url.startswith("https://")
        )

    def validate_politeness(self) -> None:
        """The 1 req/s/host floor is a hard limit; configuration may only
        make JobPilot slower, never faster."""
        if self.min_host_interval_seconds < 1.0:
            raise ValueError(
                "MIN_HOST_INTERVAL_SECONDS must be >= 1.0 — JobPilot never issues more than "
                "one request per second to a host (see docs/SOURCES.md)."
            )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_politeness()
    return s
