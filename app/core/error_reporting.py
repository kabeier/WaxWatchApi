from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.request_context import get_request_id

logger = get_logger(__name__)

try:
    import sentry_sdk as _sentry_sdk

    sentry_sdk: Any | None = _sentry_sdk
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None


def _normalized(values: Sequence[str]) -> set[str]:
    return {value.strip().lower() for value in values if value.strip()}


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request_id = get_request_id()
    tags = event.setdefault("tags", {})
    tags.setdefault("request_id", request_id)
    event.setdefault("extra", {}).setdefault("request_id", request_id)
    return event


def configure_error_reporting() -> None:
    enabled_environments = _normalized(settings.sentry_enabled_environments)
    environment = settings.environment.strip().lower()

    if not settings.sentry_dsn:
        logger.info("error_reporting.disabled", extra={"reason": "missing_dsn", "environment": environment})
        return

    if environment not in enabled_environments:
        logger.info(
            "error_reporting.disabled",
            extra={
                "reason": "environment_not_enabled",
                "environment": environment,
                "enabled_environments": sorted(enabled_environments),
            },
        )
        return

    if sentry_sdk is None:
        logger.warning("error_reporting.disabled", extra={"reason": "sentry_sdk_not_installed"})
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=_before_send,
    )
    logger.info(
        "error_reporting.enabled",
        extra={
            "environment": settings.sentry_environment or settings.environment,
            "traces_sample_rate": settings.sentry_traces_sample_rate,
        },
    )
