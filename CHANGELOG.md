# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with release dates in ISO format (`YYYY-MM-DD`).

## [Unreleased]

### Changed
- Updated provider-request summary aggregation to count `error_requests` for both HTTP failures (`status_code >= 400`) and transport/network failures where `status_code` is null but `error` is populated; added regression coverage for user and admin summary endpoints.
- Hardened CI coverage-regression fallback logic so base-vs-PR comparison is skipped with an explicit warning when base-revision DB pytest baseline generation fails, avoiding false-negative PR failures from unrelated red base commits.
- Added regression coverage for `/readyz` Postgres probing when dialect metadata is bind-owned and the connection omits transaction helpers, ensuring `SET LOCAL statement_timeout` still precedes `SELECT 1`.
- Hardened `/readyz` DB probe compatibility for lightweight/test doubles by safely handling bind-owned dialect metadata and connections that omit `in_transaction()` and/or `begin()`, while preserving Postgres `SET LOCAL statement_timeout` behavior.
- Refined `/readyz` database probing to use an in-thread short-lived bind connection and Postgres `SET LOCAL statement_timeout` before `SELECT 1`, avoiding request-scoped session handoff to worker threads while preserving readiness response compatibility.
- Enforced backend-agnostic `/readyz` DB probe timeout handling via `_run_with_timeout(...)` while retaining Postgres `SET LOCAL statement_timeout` as a secondary safeguard, and added readiness regression coverage for SQLAlchemy-failure and timeout failure reasons.
- Pinned `pip-audit` installation for CI and local `make security-deps-audit` runs via shared `PIP_AUDIT_VERSION` settings, and documented synchronized bump/maintenance expectations across governance files.
- Standardized provider retry telemetry metadata across Discogs/eBay to emit unambiguous `attempt` (current) and `attempts_total` (configured total) fields while retaining `max_attempts` as a compatibility alias, and updated provider retry assertions accordingly.
- Clarified and enforced structured logging governance synchronization so logging contract/task-orchestration/auth-observability changes are accompanied by `.env.sample`, `Makefile`, `.github/workflows/ci.yml`, docs, and changelog updates in the same PR.
- Restricted mock provider registration/default search-provider selection to explicit safe environments (`dev`, `test`, `local`) and added coverage to prevent production-like default inclusion.
- Updated scoped rate-limiter behavior so routes using `require_authenticated_principal=True` no longer bypass unauthenticated callers; missing-token requests now consume scoped anonymous (`anon:<client>`) budget and are throttled with `429` once exhausted.
- Refined scoped principal keying to prefer stable authenticated `request.state.user_id` when available, while pre-auth/invalid-bearer requests share anonymous-hybrid keys (`anon:<client>` / `anon:<client>:bearer`) so bogus token spray cannot bypass auth-required budgets.
- Deferred notification task dispatch until SQL transaction commit via session post-commit hooks, and retained failed post-commit enqueue attempts for retry on the session's next commit boundary.
- Improved notification task observability by logging structured context when delivery tasks cannot find their notification records (likely race indicator).
- Broadened `.github/workflows/secrets-scan.yml` push coverage by removing push path filters so every direct push to `main` runs Gitleaks regardless of file type.
- Hardened Discogs import queue dispatch failure handling so `/api/integrations/discogs/import` returns recoverable `503` retry guidance when task enqueue fails and persists the job as `failed_to_queue` for deterministic status polling.

### Added
- Notification service tests covering rollback-after-flush (no dispatch), successful commit (single dispatch), and failed post-commit enqueue retry behavior.

### Added
- Added a deploy-blocking `Release Gates` GitHub Actions workflow that runs perf smoke and validates scheduler/queue lag thresholds via `scripts/perf/verify_release_gates.py`.
- Added explicit release-gate threshold tables and baseline expectation guidance (including scheduler lag max and queue lag p95/p99 capture) in observability docs.
- Added measurable scaling acceptance criteria across operations/deployment docs, including explicit SLO/saturation thresholds (scheduler lag, queue backlog, DB connection utilization), baseline recording guidance, and scale-up runbook triggers for API workers, Celery concurrency, and DB pool/PgBouncer tuning.
- Added Prometheus metrics for scheduler lag, notification backlog, provider failure totals, and DB connection utilization support in `app/core/metrics.py`, with scheduler/notification instrumentation and tests verifying exposure.
- Added deterministic OpenAPI snapshot gating via `scripts/openapi_snapshot.py`, `docs/openapi.snapshot.json`, Make targets (`make openapi-snapshot` / `make check-openapi-snapshot`), and CI enforcement to objectively validate API contract drift alongside frontend contract doc sync.
- Added API request throttling with configurable global/authenticated/anonymous defaults, high-risk endpoint scopes (`/api/search`, `/api/watch-rules*`, `/api/integrations/discogs/*`, `/api/stream/events`), and standardized `429` `rate_limited` error envelopes with `Retry-After`.
- Added regression coverage proving throttled and non-throttled behavior across prioritized API scopes (`search`, `watch_rules`, `discogs`, and `stream_events`).
- Added CI hardening for throttling governance by introducing a dedicated DB-backed `tests/test_rate_limit.py` workflow step and a matching local `make test-rate-limit` helper target.
- Adjusted targeted throttling regression execution to run `alembic upgrade heads` first and execute `tests/test_rate_limit.py` with `--no-cov` plus a 240s timeout/progress flags so schema/bootstrap issues, global coverage gates, and silent hangs do not mask rate-limit contract failures.
- Added dedicated security workflows for Python CodeQL (`.github/workflows/security.yml`), dependency auditing via `pip-audit` (`.github/workflows/dependency-audit.yml`), and optional PR secret scanning via Gitleaks (`.github/workflows/secrets-scan.yml`).
- Added `push` triggers on `main` for CodeQL and Gitleaks workflows with path filters so post-merge security scans run for meaningful code/config changes while controlling CI cost.
- Added a dedicated non-blocking GitHub Actions perf smoke workflow (`.github/workflows/smoke.yml`) with environment-scoped secrets/vars and uploaded k6 summary/log artifacts for trend visibility.
- Changelog governance across contribution guidance, CI policy checks, and PR template requirements.
- Added a k6-based perf smoke harness (`make perf-smoke`) with SLO-aligned thresholds and deployment/operations run requirements.
- Added `make ci-static-checks` as the non-DB CI gate target used by both local and GitHub Actions workflows.

### Changed
- Fixed lifecycle scope backfill update predicate to treat both SQL NULL and JSONB `null` as missing scopes, addressing migration write-skips in DB CI runs.
- Refined migration `scope_normalized` CTE into single-row-per-id COALESCE priority selection to prevent non-persisted scope writes under CI DB runs.
- Added deterministic `scopes` array construction (`to_jsonb(array_remove(string_to_array(...), ''))`) in migration CTE to avoid null scope regressions in migration runtime tests.
- Stabilized token lifecycle scope-string backfill SQL using deterministic CTE normalization and expanded migration-coverage variants (whitespace, scope fallback, blank handling, idempotency).
- Aligned `scripts/perf/core_flows_smoke.js` thresholds and perf README documentation to the same read/query/write SLO gates used for release decisions, including p95/p99 latency, error-rate, and check-rate constraints.
- Expanded deployment documentation with scaling knobs for API workers, SQLAlchemy/ PgBouncer pool sizing, and Redis/Celery runtime tuning tied to release-gate reruns.
- Added Alembic merge revision `2dc6fd57f7d9` to unify previously divergent migration heads into a single tip for deterministic `alembic upgrade head` behavior.
- Pinned external GitHub Action `uses:` references in workflow/composite CI files to full commit SHAs while retaining trailing release-tag comments for maintainability, and kept `.github/dependabot.yml` GitHub Actions updates enabled for automated SHA bump PRs.
- Closed the change-surface policy gap for task orchestration updates by ensuring direct edits to `app/tasks.py` trigger governance enforcement, adding regression coverage for that trigger path, and deriving remediation messaging from the required synchronized file list.
- Added focused token lifecycle normalization unit coverage for Discogs metadata parsing/date coercion and migration extractor fallback paths to prevent coverage regression in DB CI gates.
- Hardened `external_account_links` token lifecycle persistence with normalized refresh/expiry/type/scope columns, migration backfill from legacy `token_metadata`, and Discogs token handling updates plus provider-agnostic token lifecycle helpers/tests.
- Added a follow-up token lifecycle backfill migration and Discogs runtime hydration/preservation safeguards so normalized fields stay durable even for legacy metadata-only rows and partial reconnect payloads.
- Expanded health router tests to cover `_record_db_pool_utilization` guard branches (missing pool API and non-positive pool size) to stabilize CI coverage/regression checks.
- Corrected provider failure metrics test expectation to assert the actual `ProviderError` message label (`error_type="bad request"`) emitted by current provider logging behavior.
- Wired `/metrics` collection to record `waxwatch_db_connection_utilization` from SQLAlchemy pool state so DB saturation telemetry is emitted at scrape-time.
- Hardened GitHub Actions workflows by setting explicit top-level permissions defaults and pinning core actions to immutable commit SHAs; documented SHA rotation policy and Dependabot action-update expectations in contributor guidance.
- Documented a security scanning triage/exception runbook and wired governance references into CI/Make/.env sample to keep change-surface checks synchronized.
- Split GitHub Actions CI into `static-checks` and `db-tests` jobs with shared Python setup via a composite action and `db-tests` dependency on `static-checks`.
- Kept `make ci-local` as the canonical local parity command by composing `ci-static-checks`, `ci-db-tests`, and `ci-celery-redis-smoke`.
- Added top-level CI workflow concurrency cancellation (`${{ github.workflow }}-${{ github.ref }}` + `cancel-in-progress: true`) so force-pushes and rapid PR commit bursts only keep the newest run active.
- Enhanced the non-blocking perf smoke workflow with manual dispatch overrides (`perf_base_url`, `perf_rule_id`), explicit runtime fallback resolution (dispatch input → environment variable → repository variable), and safe source diagnostics while preserving required-value hard-fail behavior.
- Documented and codified a static/policy CI pre-review expectation by clarifying `make ci-static-checks` usage across CI workflow, Makefile help, contributor guidance, and env governance notes.
- Refined static/policy governance so `.env.sample` synchronization is enforced only for environment-variable additions/removals/default changes, while other integration-surface edits continue to require Makefile/CI/docs/changelog sync.

## [0.1.0] - 2026-02-25

### Added
- Added dedicated security workflows for Python CodeQL (`.github/workflows/security.yml`), dependency auditing via `pip-audit` (`.github/workflows/dependency-audit.yml`), and optional PR secret scanning via Gitleaks (`.github/workflows/secrets-scan.yml`).
- Initial project baseline.
