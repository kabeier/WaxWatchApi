# Deployment Workflow (Runtime-Injected Secrets)

This project uses **runtime-injected environment variables** for production.

- Do **not** rely on checked-in or server-local `.env` files for production.
- Inject secrets via your CI/CD platform or secret manager (GitHub Actions secrets, AWS/GCP secret managers, Vault, etc.).
- Keep `.env.sample` as a local/dev reference only.
- Production compose is **fail-closed** for provider credentials: missing secrets stay missing and providers remain disabled.

## Environment naming and behavior

Set `ENVIRONMENT` to one of the documented values so route gating and observability behave predictably:

- `dev`, `test`, `local`: development/test environments; `/api/dev-*` routes are enabled.
- `prod`, `production`, `staging`: production-like environments; `/api/dev-*` routes are disabled.

Avoid custom aliases where possible. If you must use a non-standard value, treat it as production-like unless you explicitly intend to expose dev routes.

## Security workflow layout

Security checks are intentionally separated from the main CI job graph to keep permissions minimal and scopes explicit:

- `.github/workflows/security.yml`: CodeQL (Python) on pull requests and a weekly schedule.
- `.github/workflows/dependency-audit.yml`: `pip-audit` on dependency-file PR changes and weekly schedule.
- `.github/workflows/secrets-scan.yml`: Gitleaks secret scanning on pull requests and every direct push to `main` (no push path allowlist).

Security triage and exception handling process is documented in `docs/OPERATIONS_OBSERVABILITY.md` and should be followed for any failing security scan.

## CI job layout

GitHub Actions CI is split into two primary jobs to improve required-check granularity and time-to-first-failure:

- `static-checks`: `make ci-static-checks` (Ruff lint/format, mypy, policy/contract checks, and other non-DB gates).
- `db-tests`: `make ci-db-tests` (test DB migrations + schema drift + pytest coverage), configured to run after `static-checks`.
- Coverage regression comparison (`scripts/check_coverage_regression.py`) runs after generating base + PR coverage artifacts; if the fetched base revision cannot produce a DB pytest baseline, CI emits a warning and skips only the comparison step while preserving PR coverage gating.

`make ci-local` remains the canonical local command and composes both jobs plus `make ci-celery-redis-smoke`.

## CI worker-dependent integration smoke

The worker-dependent Celery/Redis roundtrip test is intentionally orchestrated outside default DB test discovery.

- `make ci-db-tests` ignores `tests/test_celery_redis_integration.py` so the default coverage suite does not require a live worker.
- `make ci-celery-redis-smoke` starts the dedicated worker process and sets `RUN_CELERY_REDIS_INTEGRATION=1` before running that test.

## Local development (Docker Compose)

For local development only, use the dev override and optional `.env.dev` file:

```bash
make up
```

This uses the dev compose workflow (including `docker-compose.override.yml`) and is intentionally separate from production deployment.

## Production deployment (no local env file)

Export or inject required production variables in your shell/runner environment first, then run:

```bash
make check-prod-env
make migrate-prod
make prod-up
```

`make migrate-prod` and `make prod-up` consume the current process environment (runtime injection), not `--env-file .env.prod`.

### Default required runtime variables

`make check-prod-env` requires this default set for the intended production topology:

- `DATABASE_URL`
- `AUTH_ISSUER`
- `AUTH_JWKS_URL`
- `TOKEN_CRYPTO_KMS_KEY_ID`
- `DISCOGS_USER_AGENT`
- `DISCOGS_TOKEN`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`

If your deployment topology differs, override `PROD_REQUIRED_ENV_VARS` explicitly:

```bash
make PROD_REQUIRED_ENV_VARS="DATABASE_URL AUTH_ISSUER AUTH_JWKS_URL TOKEN_CRYPTO_KMS_KEY_ID" check-prod-env
```

### Secret injection examples

Bash shell example:

```bash
export DATABASE_URL='postgresql+psycopg://...'
export AUTH_ISSUER='https://<project>.supabase.co/auth/v1'
export AUTH_JWKS_URL='https://<project>.supabase.co/auth/v1/.well-known/jwks.json'
export TOKEN_CRYPTO_KMS_KEY_ID='arn:aws:kms:us-east-1:123456789012:key/abcd-...'
export DISCOGS_USER_AGENT='waxwatch/1.0 (+ops@example.com)'
export DISCOGS_TOKEN='discogs-personal-token'
export EBAY_CLIENT_ID='ebay-client-id'
export EBAY_CLIENT_SECRET='ebay-client-secret'
make check-prod-env && make migrate-prod && make prod-up
```

GitHub Actions example:

```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  AUTH_ISSUER: ${{ secrets.AUTH_ISSUER }}
  AUTH_JWKS_URL: ${{ secrets.AUTH_JWKS_URL }}
  TOKEN_CRYPTO_KMS_KEY_ID: ${{ secrets.TOKEN_CRYPTO_KMS_KEY_ID }}
  DISCOGS_USER_AGENT: ${{ secrets.DISCOGS_USER_AGENT }}
  DISCOGS_TOKEN: ${{ secrets.DISCOGS_TOKEN }}
  EBAY_CLIENT_ID: ${{ secrets.EBAY_CLIENT_ID }}
  EBAY_CLIENT_SECRET: ${{ secrets.EBAY_CLIENT_SECRET }}
```

## Deployment checklist

Before each production deploy:

1. CI green (lint, typecheck, tests, migrations).
2. Container image built and tagged.
3. Database backup/rollback plan confirmed.
4. `make check-prod-env` passes in the deploy runtime.
   - This check **fails** if required production env vars/secrets are missing.
5. `make migrate-prod` succeeds.
6. `make prod-up` succeeds and health checks are green.
7. Post-deploy smoke test completed (`/healthz`, `/readyz`, critical API path).
   - `/healthz` must be a lightweight liveness check only.
   - `/readyz` must return `200` only when required dependencies are healthy (DB always; Redis when Celery is not eager).
8. Observability checks completed:
   - SLO dashboards are reporting (API latency by endpoint category, provider error budgets, scheduler freshness, notification lag).
   - Alert thresholds match `docs/OPERATIONS_OBSERVABILITY.md` numeric warning/critical targets.


## Performance smoke requirement

Run `make perf-smoke` for release safety in these cases:

- **Pre-release (required):** run against the release candidate environment before production rollout.
- **Post-major schema/index change (required):** run after deploying major database schema or index updates.

Required environment for `make perf-smoke`:

- `PERF_BASE_URL` (target API base URL)
- `PERF_BEARER_TOKEN` (JWT for an account with representative data)
- `PERF_RULE_ID` (rule owned by that account; optional only when `PERF_ENABLE_RULE_RUN=0`)

The harness enforces SLO-aligned thresholds for read/query/write-like flows and should be treated as a deploy-blocking check when thresholds are exceeded. Record each release-candidate baseline in `docs/OPERATIONS_OBSERVABILITY.md` (baseline snapshot table) so results stay repeatable across releases.

For release sign-off in GitHub Actions, run `.github/workflows/release-gates.yml` with observed scheduler/queue lag values from dashboards. The workflow is deploy-blocking and fails unless all release thresholds pass:
- k6 smoke thresholds from `scripts/perf/core_flows_smoke.js` (read/query/write latency + error rate),
- `scheduler_lag_p95_seconds < 60`,
- `scheduler_lag_max_seconds < 180`,
- `queue_lag_p95_seconds < 30`,
- `queue_lag_p99_seconds < 90`.

For GitHub Actions runs (`.github/workflows/smoke.yml`), `PERF_BASE_URL` and `PERF_RULE_ID` resolve in this order:
1. `workflow_dispatch` input override (`perf_base_url`, `perf_rule_id`),
2. `perf-smoke` environment variable,
3. repository variable fallback.


## Scale-up runbook triggers

Use these triggers during incident response or release validation to apply predictable scaling changes.

### API worker scale-up
- Trigger when any of the following hold for 10 minutes:
  - read p95 latency `> 400ms`, or
  - query p95 latency `> 900ms`, or
  - write p95 latency `> 700ms`, or
  - API 5xx ratio `> 1%`.
- Action:
  1. Increase API worker count by 25-50% (or +2 workers minimum).
  2. Re-run `make perf-smoke` and verify p95/p99 thresholds recover.
  3. If no improvement, investigate DB saturation before additional horizontal scale.

### Celery concurrency scale-up
- Trigger when scheduler lag or queue lag breaches for 10 minutes:
  - `waxwatch_scheduler_lag_seconds` p95 `> 60s`,
  - queue lag p95 `> 30s`, or
  - notification backlog exceeds 500 (email) / 1000 (realtime).
- Action:
  1. Increase Celery worker concurrency by 25-50%.
  2. Keep `worker_prefetch_multiplier` conservative (typically `1`) to reduce queue starvation.
  3. Validate backlog decay slope turns negative within 15 minutes.

### DB pool / PgBouncer scale-up
- Trigger when DB connection saturation persists for 10 minutes:
  - `waxwatch_db_connection_utilization` p95 `> 0.70`, or
  - utilization max `> 0.85`.
- Action:
  1. Increase API/Celery SQLAlchemy pool settings (`pool_size`, `max_overflow`) in controlled increments.
  2. Raise PgBouncer `default_pool_size` and `max_client_conn` together to preserve headroom.
  3. Ensure database `max_connections` remains above combined PgBouncer server pools plus admin margin.
  4. Re-check readiness and query latency after each increment before further scaling.

## Scaling knobs (release/incident tuning reference)

Use these knobs in controlled increments and re-run release gates after each change.

### API process and worker knobs
- `uvicorn`/process worker count (deployment runtime or process manager setting).
- Per-worker concurrency model (async workers vs. process count).
- `RATE_LIMIT_*` controls to reduce pressure while capacity recovers.

### Database and pool knobs
- SQLAlchemy engine pool knobs:
  - `pool_size`
  - `max_overflow`
  - `pool_timeout`
  - `pool_recycle`
- PgBouncer knobs (if enabled):
  - `default_pool_size`
  - `max_client_conn`
  - reserve/admin connection headroom.

### Redis/Celery knobs
- `CELERY_TASK_ALWAYS_EAGER` (must be `false` in production queue mode).
- Celery worker concurrency (`--concurrency` runtime flag).
- Celery prefetch (`worker_prefetch_multiplier`, recommended `1` for fair queueing).
- Celery queue routing and dedicated workers for long-running tasks.
- Redis capacity knobs (connection limits, memory policy, and persistence mode aligned with workload).

### Scheduler and sync knobs
- Scheduler polling cadence and due-rule batch size.
- Discogs sync cadence and batching knobs:
  - `DISCOGS_SYNC_INTERVAL_SECONDS`
  - `DISCOGS_SYNC_USER_BATCH_SIZE`
  - `DISCOGS_SYNC_JITTER_SECONDS`
  - `DISCOGS_SYNC_SPREAD_SECONDS`

Operational rule: whenever worker/pool/Redis/Celery settings are changed for scale, record the old/new values and the follow-up `release-gates` run result in the release log.

## Discogs scheduled sync tuning

The Celery beat schedule now includes `app.tasks.sync_discogs_lists` for background Discogs list refreshes.
Use conservative settings first, then scale carefully:

- `DISCOGS_SYNC_ENABLED=false` by default (recommended while validating quotas/worker capacity).
- `DISCOGS_SYNC_INTERVAL_SECONDS=3600` default cadence.
- `DISCOGS_SYNC_USER_BATCH_SIZE=25` maximum connected users discovered per run.
- `DISCOGS_SYNC_JITTER_SECONDS=30` and `DISCOGS_SYNC_SPREAD_SECONDS=5` to stagger imports and avoid burst traffic.

Operational behavior:

- Scheduler only considers active users with a connected Discogs external account link.
- Per-user cooldown and idempotent in-flight checks prevent duplicate import-job storms.
- If a user already has an in-flight/recent job in cooldown, no extra job is created.

## Change synchronization requirement

When introducing new environment variables, CI/test commands, or Make targets, update `.env.sample`, `Makefile`, `.github/workflows/ci.yml`, `CONTRIBUTING.md`, and `CHANGELOG.md` (for behavior-impacting changes) in the same PR, plus any affected docs.
CI enforces this through `python scripts/check_change_surface.py` and `python scripts/check_env_sample.py` in the workflow.


## API request throttling policy

The API enforces in-process, rolling-window request throttling for both anonymous and authenticated traffic.

- Global limits are applied to all `/api/*` requests (health/readiness/metrics are exempt).
- High-risk endpoints have tighter per-scope limits:
  - `/api/search*`
  - `/api/watch-rules*`
  - `/api/integrations/discogs/*`
  - `/api/stream/events`
- A `429` response includes `Retry-After` and a standard error envelope with `code: rate_limited`.
- Scope-specific throttles are enforced in-route for `/api/search*`, `/api/watch-rules*`, `/api/integrations/discogs/*`, and `/api/stream/events`, while global limits still apply to all `/api/*` traffic.

Environment knobs (all non-secret):

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_GLOBAL_AUTHENTICATED_RPM`, `RATE_LIMIT_GLOBAL_AUTHENTICATED_BURST`
- `RATE_LIMIT_GLOBAL_ANONYMOUS_RPM`, `RATE_LIMIT_GLOBAL_ANONYMOUS_BURST`
- `RATE_LIMIT_AUTH_ENDPOINT_RPM`, `RATE_LIMIT_AUTH_ENDPOINT_BURST`
- `RATE_LIMIT_SEARCH_RPM`, `RATE_LIMIT_SEARCH_BURST`
- `RATE_LIMIT_WATCH_RULES_RPM`, `RATE_LIMIT_WATCH_RULES_BURST`
- `RATE_LIMIT_DISCOGS_RPM`, `RATE_LIMIT_DISCOGS_BURST`
- `RATE_LIMIT_STREAM_EVENTS_RPM`, `RATE_LIMIT_STREAM_EVENTS_BURST`

Tune per environment based on expected traffic, worker capacity, and provider quota ceilings.

CI enforcement note: the database-backed CI workflow also executes `tests/test_rate_limit.py` explicitly to guard the 429 envelope and scoped-throttle contract.
