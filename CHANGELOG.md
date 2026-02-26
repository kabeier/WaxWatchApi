# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with release dates in ISO format (`YYYY-MM-DD`).

## [Unreleased]

### Added
- Added deterministic OpenAPI snapshot gating via `scripts/openapi_snapshot.py`, `docs/openapi.snapshot.json`, Make targets (`make openapi-snapshot` / `make check-openapi-snapshot`), and CI enforcement to objectively validate API contract drift alongside frontend contract doc sync.
- Added API request throttling with configurable global/authenticated/anonymous defaults, high-risk endpoint scopes (`/api/search`, `/api/watch-rules*`, `/api/integrations/discogs/*`, `/api/stream/events`), and standardized `429` `rate_limited` error envelopes with `Retry-After`.
- Added dedicated security workflows for Python CodeQL (`.github/workflows/security.yml`), dependency auditing via `pip-audit` (`.github/workflows/dependency-audit.yml`), and optional PR secret scanning via Gitleaks (`.github/workflows/secrets-scan.yml`).
- Added a dedicated non-blocking GitHub Actions perf smoke workflow (`.github/workflows/smoke.yml`) with environment-scoped secrets/vars and uploaded k6 summary/log artifacts for trend visibility.
- Changelog governance across contribution guidance, CI policy checks, and PR template requirements.
- Added a k6-based perf smoke harness (`make perf-smoke`) with SLO-aligned thresholds and deployment/operations run requirements.
- Added `make ci-static-checks` as the non-DB CI gate target used by both local and GitHub Actions workflows.

### Changed
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
