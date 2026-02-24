from __future__ import annotations

from pydantic import PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    _provider_availability: dict[str, tuple[bool, str | None]] = PrivateAttr(default_factory=dict)

    app_name: str = "watch-wax-api"
    environment: str = "dev"
    supabase_url: str | None = None

    database_url: str

    # Dev behavior flags
    dev_auto_create_users: bool = True
    dev_backfill_on_rule_change: bool = True
    dev_backfill_days: int = 7
    dev_backfill_limit: int = 500

    discogs_user_agent: str | None = None
    discogs_token: str | None = None
    discogs_timeout_seconds: float = 10.0
    discogs_max_attempts: int = 4
    discogs_retry_base_delay_ms: int = 250
    discogs_retry_max_delay_ms: int = 5_000

    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_oauth_scope: str = "https://api.ebay.com/oauth/api_scope"
    ebay_marketplace_id: str = "EBAY_US"
    ebay_timeout_seconds: float = 10.0
    ebay_max_attempts: int = 4
    ebay_retry_base_delay_ms: int = 250
    ebay_retry_max_delay_ms: int = 5_000

    ebay_campaign_id: str | None = None
    ebay_custom_id: str | None = None

    scheduler_poll_interval_seconds: int = 15
    scheduler_batch_size: int = 100
    scheduler_rule_limit: int = 20

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

    @model_validator(mode="after")
    def _validate_provider_config(self) -> Settings:
        self._provider_availability = {
            "discogs": self._validate_required_fields(
                [self.discogs_user_agent, self.discogs_token], ["discogs_user_agent", "discogs_token"]
            ),
            "ebay": self._validate_required_fields(
                [self.ebay_client_id, self.ebay_client_secret], ["ebay_client_id", "ebay_client_secret"]
            ),
            "mock": (True, None),
        }
        return self

    @staticmethod
    def _validate_required_fields(
        field_values: list[str | None],
        field_names: list[str],
    ) -> tuple[bool, str | None]:
        missing = [
            name for name, value in zip(field_names, field_values, strict=False) if not (value or "").strip()
        ]
        if not missing:
            return True, None

        return False, f"missing required config: {', '.join(missing)}"

    def provider_enabled(self, provider_name: str) -> tuple[bool, str | None]:
        return self._provider_availability.get(provider_name, (False, "provider is not configured"))


settings = Settings()
