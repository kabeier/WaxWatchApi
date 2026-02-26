from __future__ import annotations

import json

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
    discogs_oauth_client_id: str | None = None
    discogs_oauth_client_secret: str | None = None
    discogs_oauth_redirect_uri: str | None = None
    discogs_oauth_scopes: str = "identity wantlist collection"
    discogs_oauth_state_ttl_seconds: int = 600
    discogs_timeout_seconds: float = 10.0
    discogs_max_attempts: int = 4
    discogs_retry_base_delay_ms: int = 250
    discogs_retry_max_delay_ms: int = 5_000
    discogs_sync_enabled: bool = False
    discogs_sync_interval_seconds: int = 3600
    discogs_sync_user_batch_size: int = 25
    discogs_sync_jitter_seconds: int = 30
    discogs_sync_spread_seconds: int = 5

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

    notification_email_provider: str = "stub"
    ses_region: str = "us-east-1"
    ses_sender_email: str = "noreply@example.com"
    ses_configuration_set: str | None = None
    ses_endpoint_url: str | None = None

    scheduler_poll_interval_seconds: int = 15
    scheduler_batch_size: int = 100
    scheduler_rule_limit: int = 20
    scheduler_next_run_jitter_seconds: int = 5
    scheduler_failure_retry_jitter_seconds: int = 5

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True
    celery_task_retry_backoff_seconds: int = 5
    celery_task_max_retries: int = 4
    celery_worker_prefetch_multiplier: int = 1
    celery_worker_max_tasks_per_child: int = 100

    # Error reporting
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_enabled_environments: list[str] = ["staging", "prod"]
    sentry_traces_sample_rate: float = 0.0

    # Logging
    log_level: str = "INFO"
    json_logs: bool = True

    # CORS
    cors_allowed_origins: list[str] = []
    cors_allowed_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_allowed_headers: list[str] = ["Authorization", "Content-Type"]
    cors_allow_credentials: bool = False

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_global_authenticated_rpm: int = 120
    rate_limit_global_authenticated_burst: int = 30
    rate_limit_global_anonymous_rpm: int = 60
    rate_limit_global_anonymous_burst: int = 10
    rate_limit_auth_endpoint_rpm: int = 20
    rate_limit_auth_endpoint_burst: int = 5
    # High-risk endpoint scopes
    # - /api/search*
    rate_limit_search_rpm: int = 30
    rate_limit_search_burst: int = 10
    # - /api/watch-rules*
    rate_limit_watch_rules_rpm: int = 60
    rate_limit_watch_rules_burst: int = 20
    # - /api/integrations/discogs/*
    rate_limit_discogs_rpm: int = 30
    rate_limit_discogs_burst: int = 10
    # - /api/stream/events
    rate_limit_stream_events_rpm: int = 12
    rate_limit_stream_events_burst: int = 2

    # Token crypto (at-rest encryption for provider credentials)
    token_crypto_kms_key_id: str | None = None
    token_crypto_local_key_path: str | None = None
    token_crypto_local_key: str | None = None

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
        self.cors_allowed_origins = self._parse_env_list(self.cors_allowed_origins)
        self.cors_allowed_methods = self._parse_env_list(self.cors_allowed_methods)
        self.cors_allowed_headers = self._parse_env_list(self.cors_allowed_headers)
        self.sentry_enabled_environments = self._parse_env_list(self.sentry_enabled_environments)

        if self.cors_allow_credentials and any(origin == "*" for origin in self.cors_allowed_origins):
            raise ValueError("cors_allowed_origins cannot include '*' when cors_allow_credentials is true")

        if self.cors_allow_credentials and any(method == "*" for method in self.cors_allowed_methods):
            raise ValueError("cors_allowed_methods cannot include '*' when cors_allow_credentials is true")

        if self.cors_allow_credentials and any(header == "*" for header in self.cors_allowed_headers):
            raise ValueError("cors_allowed_headers cannot include '*' when cors_allow_credentials is true")

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

    @staticmethod
    def _parse_env_list(raw_value: list[str] | str) -> list[str]:
        if isinstance(raw_value, list):
            return [item.strip() for item in raw_value if item.strip()]

        value = raw_value.strip()
        if not value:
            return []

        if value.startswith("["):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("list config must deserialize to a list")
            return [str(item).strip() for item in parsed if str(item).strip()]

        return [item.strip() for item in value.split(",") if item.strip()]

    def provider_enabled(self, provider_name: str) -> tuple[bool, str | None]:
        return self._provider_availability.get(provider_name, (False, "provider is not configured"))


settings = Settings()
