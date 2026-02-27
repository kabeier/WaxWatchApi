# Contributing

## Local developer workflow

Use the same commands that CI uses before opening a pull request:

1. Install dependencies:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements-dev.txt
   pip install -e .
   ```
2. Run the full CI-equivalent local gate:
   ```bash
   make ci-local
   ```

`make ci-local` mirrors the CI gates and runs:

- `make ci-static-checks` (non-DB checks)
- `make ci-db-tests` (DB migration/drift + pytest coverage)
- `make ci-celery-redis-smoke` (worker-backed integration smoke)

- Docker compose render validation (`make check-docker-config`)
- Environment/governance sync checks (`make check-policy-sync`, which includes `make check-change-surface`)
- Frontend API contract sync check (`python scripts/check_frontend_contract_sync.py`)
- Ruff lint (`ruff check .`)
- Ruff format check (`ruff format --check .`)
- Mypy type checks (`mypy app scripts tests`)
- Alembic migration check against test DB
- Schema drift check
- Pytest with coverage collection and threshold enforcement (`--cov-fail-under=85` by default)
- Dedicated orchestrated Celery/Redis smoke test (`make ci-celery-redis-smoke`, backed by `scripts/ci_celery_redis_smoke.sh`)

### CI trigger intent and enforcement
- Performance smoke automation is intentionally isolated in `.github/workflows/smoke.yml` so remote staging instability never blocks core PR CI merges.

The CI workflow (`.github/workflows/ci.yml`) is intentionally triggered by four events and split into granular required-check jobs (`static-checks` and `db-tests`) so contributors get faster first-failure feedback:

- `pull_request` targeting `main`: primary branch-protection gate for code review merges.
- `push` to `main`: post-merge protection to ensure the default branch always satisfies the full CI suite.
- `workflow_dispatch`: manual reruns/debugging for flaky infrastructure or one-off verification.
- `schedule` (weekly): periodic maintenance execution for governance drift checks, dependency sanity, and smoke coverage even when no PRs are open.
- Top-level workflow `concurrency` uses `${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`, so force-pushes and rapid commit sequences on the same PR ref cancel superseded runs and keep required checks pinned to the newest commit.

If your change affects CI behavior or governance policy, update this section alongside `.github/workflows/ci.yml` in the same PR.

Security checks are additionally split into dedicated workflows for least-privilege operation:

- `.github/workflows/security.yml` (CodeQL for Python on PR + weekly cadence)
- `.github/workflows/dependency-audit.yml` (`pip-audit` on `requirements*.in/txt` changes + weekly cadence)
- `.github/workflows/secrets-scan.yml` (Gitleaks on PRs)

Action pin governance: keep marketplace actions SHA-pinned with version comments (for example `# v6.0.2`) when rotating versions, and update `.env.sample`, `Makefile`, and `CHANGELOG.md` in the same PR so policy-sync checks remain green.

For local parity, use `make security-deps-audit` and `make security-secrets-scan` before opening security-sensitive PRs.


## Performance smoke workflow

For release-focused or persistence-heavy changes, run the perf smoke harness before handoff:

```bash
PERF_BASE_URL=http://127.0.0.1:8000 \
PERF_BEARER_TOKEN='<jwt>' \
PERF_RULE_ID='<uuid>' \
make perf-smoke
```

The harness validates core authenticated list, rule polling, and provider-request logging flows using SLO-aligned latency/error thresholds (p95+p99 latency per flow, `<1%` request failures, and `>99%` k6 check pass-rate). See `scripts/perf/README.md` and `docs/OPERATIONS_OBSERVABILITY.md` for thresholds and ownership/cadence expectations.

GitHub Actions (`.github/workflows/smoke.yml`) also supports manual run-time overrides via `workflow_dispatch` inputs:
- `perf_base_url`
- `perf_rule_id`

Runtime fallback precedence in the workflow is fixed:
1. `workflow_dispatch` input,
2. `perf-smoke` environment variable,
3. repository variable fallback.

Deploy-blocking release validation uses `.github/workflows/release-gates.yml`, which runs `make perf-smoke` and then verifies scheduler/queue lag inputs provided at dispatch time (`scheduler_lag_p95_seconds`, `scheduler_lag_max_seconds`, `queue_lag_p95_seconds`, `queue_lag_p99_seconds`).

## Coverage policy

- Coverage gating is aligned between `pytest.ini`, `Makefile`, and CI (`.github/workflows/ci.yml`) with a default floor of **85%** (`--cov-fail-under=85`).
- Coverage uplift is phased:
  - **Phase 1 (active):** keep total coverage at or above **85%**.
  - **Phase 2 (target):** raise the shared floor to **88%+** after low-coverage modules are improved.
- Pull requests must not reduce overall coverage compared to the base branch.
- Pull requests must not reduce coverage for high-risk modules:
  - `app/services/background.py`
  - `app/services/watch_rules.py`
  - `app/services/matching.py`
  - `app/core/token_crypto.py`
- On pull-request CI runs, the workflow enforces non-regression with this exact sequence:
  1. Run `make ci-local` on the PR revision to generate `coverage.json`.
  2. Fetch and check out the base branch commit from `github.base_ref`.
  3. Run `make ci-local` on the base revision to generate `coverage.base.json`.
  4. Check out the PR revision again, restore `coverage.json`, then run `python scripts/check_coverage_regression.py`.
  5. Fail the job when total coverage or any listed high-risk module coverage is lower than base.
- CI triggers run once per PR update (`pull_request`) and also on direct pushes to `main` (`push`), avoiding duplicate push+PR runs for feature branches.
- `make ci-local` is the canonical CI contract target invoked by both local developers and GitHub Actions.
- `make ci-db-tests` remains the database-backed test segment used by `ci-local` and must keep migration + drift + full pytest discovery with coverage.
- Focused targets (for example `make test-matching`, `make test-token-security`) are local debugging helpers only and are non-authoritative for CI pass/fail.

## Pre-commit hooks

This repository ships pre-commit configuration in `.pre-commit-config.yaml`.

Install hooks locally:

```bash
make pre-commit-install
```

The configured hooks are:

- **pre-commit**: `ruff`, `ruff-format`, `mypy`
- **pre-push**: `make ci-local` (full CI-equivalent suite)

You can run hooks on demand:

```bash
pre-commit run --all-files
pre-commit run --hook-stage pre-push --all-files
```

Following this workflow ensures your branch meets the same lint, formatting, typing, migration, and coverage gates that run in CI.

Note: `tests/test_celery_redis_integration.py` is orchestrated-only and gated by `RUN_CELERY_REDIS_INTEGRATION=1`, which is set by `make ci-celery-redis-smoke`.

## Lockfile refresh workflow (Python 3.12)

Lockfiles must be generated with **Python 3.12** so local output matches CI/deployment markers and headers.

1. Ensure tooling is available for Python 3.12:
   ```bash
   python3.12 -m pip install pip-tools
   ```
2. Refresh both lockfiles from their `.in` sources:
   ```bash
   make lock-refresh
   ```
   This runs:
   - `requirements.in -> requirements.txt`
   - `requirements-dev.in -> requirements-dev.txt`
3. Validate lockfile headers before commit:
   ```bash
   make check-lock-python-version
   ```

CI also runs `make check-lock-python-version`, so PRs fail if lockfiles were generated with the wrong Python major/minor version.


### Ruff remediation quick path

If Ruff checks fail, apply fixes quickly and re-run gates:

```bash
make lint FIX=1
make fmt
make lint
make fmt-check
```

For stronger local enforcement on every branch, run `make pre-commit-install` so pre-commit/pre-push hooks run `ruff check .` and `ruff format --check .` automatically.


## GitHub Actions pinning policy

To reduce CI supply-chain risk, all third-party GitHub Actions must be pinned to full commit SHAs (not mutable tags alone).

When rotating pinned SHAs:

1. Keep the semantic version in an inline comment for readability (for example `# v4`).
2. Update the `uses:` reference to the new SHA in workflow/composite action files.
3. Re-run local quality gates:
   ```bash
   make lint
   make fmt-check
   ```
4. Keep Dependabot GitHub Actions updates enabled in `.github/dependabot.yml` so SHA bumps are proposed automatically.

## Product/API contract checklist

When your PR changes API-facing code in `app/api/` or `app/schemas/`, complete this checklist:

- [ ] Update `docs/FRONTEND_API_CONTRACT.md`.
- [ ] Bump/refresh the contract version field at the top of `docs/FRONTEND_API_CONTRACT.md`.
- [ ] Add a changelog entry in `CHANGELOG.md` for endpoint or schema changes.
- [ ] If behavior is breaking, document deprecation timeline under the breaking-change rules.
- [ ] Run `make check-contract-sync` and `make check-openapi-snapshot` (or `make ci-local`) before pushing.

## Changelog update policy

Use `CHANGELOG.md` for all user-visible or operator-visible behavior changes.

Required updates in `CHANGELOG.md` (same PR):

- API behavior changes under `app/api/**` or `app/schemas/**`.
- Runtime behavior changes under `app/services/**`, `app/core/config.py`, `Makefile`, or `.github/workflows/ci.yml`.
- Migration-affecting database changes (for example Alembic revisions, schema behavior changes, or data migration behavior).

Formatting/versioning rules:

- Keep a top `## [Unreleased]` section and categorize changes under Keep-a-Changelog headings (`Added`, `Changed`, `Fixed`, `Removed`, `Deprecated`, `Security`).
- On release, promote entries using semantic versions with ISO date headers (for example: `## [0.1.1] - 2026-02-26`).

Expected update workflow:

1. Implement API/schema changes.
2. Update `docs/FRONTEND_API_CONTRACT.md` in the same PR.
3. Before commiting, run Ruff lint and format checks locally (`make lint` and `make fmt-check`, or `make ci-local`).
4. Run local checks (`make lint`, `make fmt-check`, `make check-contract-sync`, `make check-openapi-snapshot`, or `make ci-local`).
5. Push only when Ruff lint and Ruff format checks pass for all commits in the PR.

Provider/source contract note:

- Treat provider-facing API fields (for example `watch_search_rules.query.sources` and `/api/me` integration summaries) as **registry-backed**. They represent only providers registered and enabled by runtime configuration, not every value in `models.Provider` / DB enum.
- When changing provider enablement rules or registration behavior, update tests and contract docs in the same PR so frontend choices stay aligned with backend-accepted sources.
- Mock provider safety: default provider resolution must exclude `mock` in production-like environments; only dev/test/local contexts should auto-enable it unless explicit provider config gates say otherwise.

## Environment configuration policy

- `.env.sample` is documentation for local/dev values only.
- Local Docker Compose development may use `.env.dev` via `docker-compose.override.yml`.
- Production deployments must inject environment variables/secrets at runtime (CI/CD secrets or secret manager), not local `.env` files.
- Use `make check-prod-env` before `make migrate-prod` / `make prod-up` to fail fast if required production variables are missing.

## Upstream change synchronization policy

Any upstream change that affects tests, CI workflow behavior, Make targets, or environment variables **must** update the governance files in the same PR:

- `.env.sample` (with non-secret defaults and env notes)
- `Makefile`
- `.github/workflows/ci.yml`
- `CONTRIBUTING.md`
- any affected operational/API docs (`docs/DEPLOYMENT.md`, `docs/FRONTEND_API_CONTRACT.md`)

Enforcement notes:

- CI runs `python scripts/check_env_sample.py` to verify `.env.sample` still covers all `Settings` fields.
- CI runs `python scripts/check_change_surface.py` to enforce integration hygiene when a PR touches testing workflow, CI config, task orchestration, or settings surfaces.
- The change-surface check requires same-PR updates to `Makefile`, `.github/workflows/ci.yml`, `.env.sample`, `CHANGELOG.md`, and relevant docs (`CONTRIBUTING.md` or `docs/*.md`).
- Exception: change-surface-triggered PRs that are strictly test/governance-only (no API/runtime/migration-affecting behavior changes) may omit `CHANGELOG.md`.
- CI also runs `python scripts/check_frontend_contract_sync.py`, which fails if changes under `app/api/` or `app/schemas/` do not include a same-PR update to `docs/FRONTEND_API_CONTRACT.md`.
- This includes non-schema router changes (for example health/metrics behavior updates) because frontend contract changelog must track API-facing adjustments.
- When health/metrics router behavior changes, keep targeted tests updated for scrape-time metric branches to avoid silent coverage regressions in CI.
- CI also runs `python -m scripts.openapi_snapshot --check`, which fails when generated OpenAPI output from `app/main.py` differs from `docs/openapi.snapshot.json`.

### Change-surface remediation checklist

If `scripts/check_change_surface.py` fails:

1. Confirm your PR touches one of the guarded surfaces (tests, CI workflow/config, orchestration, or settings).
2. Add/update the synchronized governance files in the same PR:
   - `Makefile`
   - `.github/workflows/ci.yml`
   - `.env.sample`
   - `CHANGELOG.md` (unless the test/governance-only exception applies)
   - `CONTRIBUTING.md` and/or relevant `docs/*.md`
3. Re-run locally:
   ```bash
   make check-change-surface
   make ci-local
   ```
4. If the surface change was accidental, revert it instead of bypassing the policy.


## API throttling contribution notes

When updating request throttling behavior, keep these surfaces synchronized in the same PR:

- `app/core/config.py` and `.env.sample` for any new/renamed rate-limit settings.
- `docs/DEPLOYMENT.md` for operator tuning guidance.
- `docs/FRONTEND_API_CONTRACT.md` for `429` client expectations (`Retry-After`, envelope shape, backoff guidance).
- `CHANGELOG.md` under `Unreleased`.

Always add/adjust tests under `tests/` for both limit-exceeded and exempt-path behavior.
- For scoped dependencies that set `require_authenticated_principal=True`, verify unauthenticated calls still consume scoped budget (anonymous keying) and can return `429` before auth dependency rejection on subsequent attempts.

## Integration hygiene reminder

When a change touches integration surfaces (tests, CI workflow, task orchestration, or settings), update governance files together in the same PR: `Makefile`, `.github/workflows/ci.yml`, `.env.sample`, `CHANGELOG.md`, and relevant contributor/operator documentation.


- Rate-limit behavior changes should include/refresh `tests/test_rate_limit.py` and keep CI/local governance hooks (`make test-rate-limit`, `.github/workflows/ci.yml`) synchronized in the same PR.

- For provider token lifecycle work, keep normalized `external_account_links` fields and migration backfills aligned; call out any no-new-config behavior in `.env.sample` and CHANGELOG entries.

- Migration test-path changes (including token lifecycle SQL backfills) must update governance files/docs/CHANGELOG together for policy-sync compliance.

- Policy sync: even migration test-path-only token lifecycle edits must update governance artifacts (`.env.sample`, `Makefile`, CI workflow), docs, and `CHANGELOG.md`.

- Token lifecycle migration SQL refactors (especially scope normalization CTE changes) must include synchronized governance/docs/changelog updates and DB-backed test verification.

- For JSON/JSONB lifecycle columns, verify test setup writes SQL NULL (or migration handles JSON `null`) to avoid false negatives in DB-backed migration assertions.

- Notification delivery enqueueing is commit-boundary aware; when changing notification/task orchestration, validate post-commit dispatch and missing-notification logging behavior.
