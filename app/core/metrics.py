from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

REQUEST_LATENCY_SECONDS = Histogram(
    "waxwatch_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path", "status_code"),
)

PROVIDER_CALL_RESULTS_TOTAL = Counter(
    "waxwatch_provider_call_results_total",
    "Provider call results by outcome",
    labelnames=("provider", "outcome", "status_code"),
)

SCHEDULER_RULE_OUTCOMES_TOTAL = Counter(
    "waxwatch_scheduler_rule_outcomes_total",
    "Scheduler rule execution outcomes",
    labelnames=("outcome",),
)

SCHEDULER_RUNS_TOTAL = Counter(
    "waxwatch_scheduler_runs_total",
    "Scheduler polling run count",
    labelnames=("outcome",),
)

SCHEDULER_LAG_SECONDS = Histogram(
    "waxwatch_scheduler_lag_seconds",
    "Scheduler lag in seconds between scheduled and actual execution start",
)

NOTIFICATION_BACKLOG_ITEMS = Gauge(
    "waxwatch_notification_backlog_items",
    "Number of notifications currently pending delivery",
    labelnames=("channel",),
)

DB_CONNECTION_UTILIZATION = Gauge(
    "waxwatch_db_connection_utilization",
    "Database connection pool utilization ratio",
)

LISTING_MATCH_DECISIONS_TOTAL = Counter(
    "waxwatch_listing_match_decisions_total",
    "Listing Discogs mapping decisions by outcome",
    labelnames=("outcome",),
)

LISTING_MATCH_QUALITY_PROXY_TOTAL = Counter(
    "waxwatch_listing_match_quality_proxy_total",
    "Proxy quality counters for listing Discogs mapping",
    labelnames=("metric",),
)

PROVIDER_FAILURES_TOTAL = Counter(
    "waxwatch_provider_failures_total",
    "Provider call failures by provider, status code, and error class",
    labelnames=("provider", "status_code", "error_type"),
)


def record_request_latency(*, method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUEST_LATENCY_SECONDS.labels(method=method, path=path, status_code=str(status_code)).observe(
        duration_seconds
    )


def record_provider_call_result(*, provider: str, status_code: int | None, error: str | None) -> None:
    if error:
        outcome = "error"
    elif status_code is not None and 200 <= status_code < 300:
        outcome = "success"
    else:
        outcome = "unknown"

    PROVIDER_CALL_RESULTS_TOTAL.labels(
        provider=provider,
        outcome=outcome,
        status_code=str(status_code) if status_code is not None else "none",
    ).inc()

    if outcome == "error":
        PROVIDER_FAILURES_TOTAL.labels(
            provider=provider,
            status_code=str(status_code) if status_code is not None else "none",
            error_type=error or "unknown",
        ).inc()


def record_scheduler_rule_outcome(*, success: bool) -> None:
    SCHEDULER_RULE_OUTCOMES_TOTAL.labels(outcome="success" if success else "failed").inc()


def record_scheduler_run(*, failed_rules: int) -> None:
    SCHEDULER_RUNS_TOTAL.labels(outcome="failed" if failed_rules else "success").inc()


def record_scheduler_lag(*, lag_seconds: float) -> None:
    SCHEDULER_LAG_SECONDS.observe(max(lag_seconds, 0.0))


def set_notification_backlog(*, channel: str, pending_count: int) -> None:
    NOTIFICATION_BACKLOG_ITEMS.labels(channel=channel).set(max(pending_count, 0))


def set_db_connection_utilization(*, utilization_ratio: float) -> None:
    DB_CONNECTION_UTILIZATION.set(min(max(utilization_ratio, 0.0), 1.0))


def record_listing_match_decision(*, outcome: str) -> None:
    LISTING_MATCH_DECISIONS_TOTAL.labels(outcome=outcome).inc()


def record_listing_match_quality_proxy(*, metric: str) -> None:
    LISTING_MATCH_QUALITY_PROXY_TOTAL.labels(metric=metric).inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
