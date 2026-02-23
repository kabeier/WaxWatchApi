from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "watch-wax-api"
    environment: str = "dev"
    supabase_url: str | None = None

    database_url: str

    # Dev behavior flags
    dev_auto_create_users: bool = True
    dev_backfill_on_rule_change: bool = True
    dev_backfill_days: int = 7
    dev_backfill_limit: int = 500

    discogs_user_agent: str
    discogs_token: str

    # Logging
    log_level: str = "INFO"
    json_logs: bool = True

    # Auth (Supabase JWT)
    auth_issuer: str | None = None
    auth_audience: str = "authenticated"
    auth_jwks_url: str | None = None
    auth_jwt_algorithms: list[str] = ["RS256"]
    auth_jwks_cache_ttl_seconds: int = 300
    auth_clock_skew_seconds: int = 30

    # DB pooling
    # - "null" Supabase / pgbouncer handles pooling
    # - "queue"  for  Postgres
    db_pool: str = "queue"  # dev default
    db_pool_size: int = 5
    db_max_overflow: int = 10


settings = Settings()
