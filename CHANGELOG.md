# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with release dates in ISO format (`YYYY-MM-DD`).

## [Unreleased]

### Added
- Added measurable scaling acceptance criteria across operations/deployment docs, including explicit SLO/saturation thresholds (scheduler lag, queue backlog, DB connection utilization), baseline recording guidance, and scale-up runbook triggers for API workers, Celery concurrency, and DB pool/PgBouncer tuning.
- Added Prometheus metrics for scheduler lag, notification backlog, provider failure totals, and DB connection utilization support in `app/core/metrics.py`, with scheduler/notification instrumentation and tests verifying exposure.
- Added deterministic OpenAPI snapshot gating via `scripts/openapi_snapshot.py`, `docs/openapi.snapshot.json`, Make targets (`make openapi-snapshot` / `make check-openapi-snapshot`), and CI enforcement to objectively validate API contract drift alongside frontend contract doc sync.
- Added API request throttling with configurable global/authenticated/anonymous defaults, high-risk endpoint scopes (`/api/search`, `/api/watch-rules*`, `/api/integrations/discogs/*`, `/api/stream/events`), and standardized `429` `rate_limited` error envelopes with `Retry-After`.
- Added dedicated security workflows for Python CodeQL (`.github/workflows/security.yml`), dependency auditing via `pip-audit` (`.github/workflows/dependency-audit.yml`), and optional PR secret scanning via Gitleaks (`.github/workflows/secrets-scan.yml`).
- Added a dedicated non-blocking GitHub Actions perf smoke workflow (`.github/workflows/smoke.yml`) with environment-scoped secrets/vars and uploaded k6 summary/log artifacts for trend visibility.
- Changelog governance across contribution guidance, CI policy checks, and PR template requirements.
- Added a k6-based perf smoke harness (`make perf-smoke`) with SLO-aligned thresholds and deployment/operations run requirements.
- Added `make ci-static-checks` as the non-DB CI gate target used by both local and GitHub Actions workflows.

### Changed
- Hardened `external_account_links` token lifecycle persistence with normalized refresh/expiry/type/scope columns, migration backfill from legacy `token_metadata`, and Discogs token handling updates plus provider-agnostic token lifecycle helpers/tests.
- Expanded health router tests to cover `_record_db_pool_utilization` guard branches (missing pool API and non-positive pool size) to stabilize CI coverage/regression checks.
- Corrected provider failure metrics test expectation to assert the actual `ProviderError` message label (`error_type="bad request"`) emitted by current provider logging behavior.
- Wired `/metrics` collection to record `waxwatch_db_connection_utilization` from SQLAlchemy pool state so DB saturation telemetry is emitted at scrape-time.
- Hardened GitHub Actions workflows by setting explicit top-level permissions defaults and pinning core actions to immutable commit SHAs; documented SHA rotation policy and Dependabot action-update expectations in contributor guidance.
- Documented a security scanning triage/exception runbook and wired governance references into CI/Make/.env sample to keep change-surface checks synchronized.
- Split GitHub Actions CI into `static-checks` and `db-tests` jobs with shared Python setup via a composite action and `db-tests` dependency on `static-checks`.
- Kept `make ci-local` as the canonical local parity command by composing `ci-static-checks`, `ci-db-tests`, and `ci-celery-redis-smoke`.
- Added top-level CI workflow concurrency cancellation (`${{ github.workflow }}-${{ github.ref }}` + `cancel-in-progress: true`) so force-pushes and rapid PR commit bursts only keep the newest run active.
- Enhanced the non-blocking perf smoke workflow with manual dispatch overrides (`perf_base_url`, `perf_rule_id`), explicit runtime fallback resolution (dispatch input → environment variable → repository variable), and safe source diagnostics while preserving required-value hard-fail behavior.

## [0.1.0] - 2026-02-25

### Added
- Added dedicated security workflows for Python CodeQL (`.github/workflows/security.yml`), dependency auditing via `pip-audit` (`.github/workflows/dependency-audit.yml`), and optional PR secret scanning via Gitleaks (`.github/workflows/secrets-scan.yml`).
- Initial project baseline.
