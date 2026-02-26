# Performance smoke harness

This folder contains a lightweight `k6` smoke harness for core API flows:

- authenticated list endpoints,
- rule polling task path,
- provider request logging write path.

## Prerequisites

- A running API deployment (`PERF_BASE_URL`).
- A valid JWT bearer token for a user with data (`PERF_BEARER_TOKEN`).
- A rule ID owned by that user for the rule polling scenario (`PERF_RULE_ID`).
  - If your environment does not expose `/api/dev/rules/{rule_id}/run`, set `PERF_ENABLE_RULE_RUN=0` to skip that scenario.

## Run directly with k6

```bash
PERF_BASE_URL=http://127.0.0.1:8000 \
PERF_BEARER_TOKEN='<jwt>' \
PERF_RULE_ID='<uuid>' \
k6 run scripts/perf/core_flows_smoke.js
```

## Run via Make

Use `make perf-smoke` to run the same script with defaults and support for either local `k6` or the `grafana/k6` Docker image.

```bash
PERF_BASE_URL=http://127.0.0.1:8000 \
PERF_BEARER_TOKEN='<jwt>' \
PERF_RULE_ID='<uuid>' \
make perf-smoke
```

## Acceptance thresholds (SLO-aligned)

- `auth_list` scenario:
  - `http_req_duration` p95 `< 400ms`
  - `http_req_failed` rate `< 1%`
- `rule_poll` scenario:
  - `http_req_duration` p95 `< 900ms`
  - `http_req_failed` rate `< 1%`
- `provider_log_write` scenario:
  - `http_req_duration` p95 `< 700ms`
  - `http_req_failed` rate `< 1%`

These thresholds mirror the read/query/write latency and availability guardrails in `docs/OPERATIONS_OBSERVABILITY.md`.

## GitHub Actions smoke workflow

A dedicated workflow at `.github/workflows/smoke.yml` runs `make perf-smoke` outside core PR CI so remote-environment flakiness does not block merges.

- Triggers: `workflow_dispatch` (manual) and weekly `schedule`.
- Environment scope: configure a GitHub Environment (for example `perf-smoke`) with:
  - required variable `PERF_BASE_URL`,
  - required secret `PERF_BEARER_TOKEN`,
  - optional variable `PERF_RULE_ID` (set `PERF_ENABLE_RULE_RUN=0` in the environment to skip rule-run checks when absent).
- Artifacts: each run uploads `artifacts/perf/k6-summary.json` and `artifacts/perf/perf-smoke.log` for trend review and incident triage.
