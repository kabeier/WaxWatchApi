#!/usr/bin/env python3
"""Verify release gates from perf smoke summary + scheduler/queue lag metrics."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REQUIRED_ENV = (
    "SCHEDULER_LAG_P95_SECONDS",
    "SCHEDULER_LAG_MAX_SECONDS",
    "QUEUE_LAG_P95_SECONDS",
    "QUEUE_LAG_P99_SECONDS",
)

GATES = {
    "scheduler_lag_p95": ("SCHEDULER_LAG_P95_SECONDS", 60.0),
    "scheduler_lag_max": ("SCHEDULER_LAG_MAX_SECONDS", 180.0),
    "queue_lag_p95": ("QUEUE_LAG_P95_SECONDS", 30.0),
    "queue_lag_p99": ("QUEUE_LAG_P99_SECONDS", 90.0),
}


def _parse_float(name: str) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"missing required environment variable: {name}")
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric, got: {value!r}") from exc


def _load_summary(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"k6 summary file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    metrics = data.get("metrics", {})
    thresholds_failed = [
        metric_name
        for metric_name, metric in metrics.items()
        if any(not result.get("ok", False) for result in metric.get("thresholds", {}).values())
    ]
    if thresholds_failed:
        raise ValueError(
            "k6 thresholds failed for metrics: "
            + ", ".join(sorted(thresholds_failed))
            + ". Fix perf smoke regressions before release."
        )
    return data


def main() -> int:
    summary_path = Path(os.getenv("K6_SUMMARY_PATH", "artifacts/perf/k6-summary.json"))

    try:
        _load_summary(summary_path)
        current = {name: _parse_float(env_name) for name, (env_name, _limit) in GATES.items()}
    except ValueError as err:
        print(f"release gate validation failed: {err}", file=sys.stderr)
        return 1

    failed = []
    for gate_name, (_env_name, limit) in GATES.items():
        value = current[gate_name]
        if value >= limit:
            failed.append(f"{gate_name}={value:.3f} (must be < {limit:.3f})")

    if failed:
        print("release gate validation failed:", file=sys.stderr)
        for line in failed:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("release gates passed: k6 thresholds + scheduler/queue lag limits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
