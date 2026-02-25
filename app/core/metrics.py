from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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


def record_scheduler_rule_outcome(*, success: bool) -> None:
    SCHEDULER_RULE_OUTCOMES_TOTAL.labels(outcome="success" if success else "failed").inc()


def record_scheduler_run(*, failed_rules: int) -> None:
    SCHEDULER_RUNS_TOTAL.labels(outcome="failed" if failed_rules else "success").inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
