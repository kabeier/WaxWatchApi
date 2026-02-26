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
  - `http_req_duration` p95 `< 400ms`, p99 `< 700ms`
  - `http_req_failed` rate `< 1%`
  - `checks` rate `> 99%`
- `rule_poll` scenario:
  - `http_req_duration` p95 `< 900ms`, p99 `< 1200ms`
  - `http_req_failed` rate `< 1%`
  - `checks` rate `> 99%`
- `provider_log_write` scenario:
  - `http_req_duration` p95 `< 700ms`, p99 `< 1000ms`
  - `http_req_failed` rate `< 1%`
  - `checks` rate `> 99%`

These thresholds mirror the read/query/write latency and availability guardrails in `docs/OPERATIONS_OBSERVABILITY.md`.

## GitHub Actions smoke workflow

A dedicated workflow at `.github/workflows/smoke.yml` runs `make perf-smoke` outside core PR CI so remote-environment flakiness does not block merges.

### 1) One-time GitHub setup

1. Create (or reuse) a GitHub Environment named `perf-smoke`.
2. In **Settings → Secrets and variables → Actions** configure:
   - **Environment secret** in `perf-smoke`:
     - `PERF_BEARER_TOKEN` (**required**)
   - **Environment variables** in `perf-smoke`:
     - `PERF_BASE_URL` (**recommended default**)
     - `PERF_RULE_ID` (optional)
   - **Repository variables** (fallback when environment vars are absent):
     - `PERF_BASE_URL` (fallback)
     - `PERF_RULE_ID` (optional fallback)

### 2) Runtime resolution order

For `PERF_BASE_URL` and `PERF_RULE_ID`, the workflow resolves values in this exact order:

1. `workflow_dispatch` input override,
2. environment variable from `perf-smoke`,
3. repository variable fallback.

The workflow prints a safe diagnostic summary showing whether each required value is set and which source was selected. Secret values are never printed.

### 3) Run manually (workflow_dispatch)

1. Open **Actions → Performance Smoke → Run workflow**.
2. Optionally provide:
   - `perf_base_url` to override `PERF_BASE_URL` for this run only,
   - `perf_rule_id` to override `PERF_RULE_ID` for this run only.
3. Click **Run workflow**.

### 4) Scheduled run

- The workflow also runs weekly via cron (`0 13 * * 2`).

### 5) Validation and failure behavior

- Hard-fail conditions:
  - `PERF_BASE_URL` unresolved after fallback.
  - `PERF_BEARER_TOKEN` missing.
- `PERF_RULE_ID` is optional (set `PERF_ENABLE_RULE_RUN=0` to skip rule-run checks when absent in your target environment).

### 6) Artifacts

Each run uploads:

- `artifacts/perf/k6-summary.json`
- `artifacts/perf/perf-smoke.log`

Use these artifacts for trend review and incident triage.

## Release-gate validation

Use `scripts/perf/verify_release_gates.py` after the smoke run to combine k6 threshold status with scheduler/queue lag dashboard inputs:

```bash
SCHEDULER_LAG_P95_SECONDS=12 \
SCHEDULER_LAG_MAX_SECONDS=45 \
QUEUE_LAG_P95_SECONDS=8 \
QUEUE_LAG_P99_SECONDS=20 \
python scripts/perf/verify_release_gates.py
```

This script is used by `.github/workflows/release-gates.yml` and fails the release gate when any threshold is breached.
