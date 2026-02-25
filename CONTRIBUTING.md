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

- Frontend API contract sync check (`python scripts/check_frontend_contract_sync.py`)
- Ruff lint (`ruff check .`)
- Ruff format check (`ruff format --check .`)
- Mypy type checks (`mypy app scripts tests`)
- Alembic migration check against test DB
- Schema drift check
- Pytest with coverage collection and threshold enforcement (`--cov-fail-under=75` by default)

## Coverage threshold policy

- CI enforces a minimum line coverage threshold through `make ci-db-tests` using `--cov-fail-under=$(COVERAGE_FAIL_UNDER)`.
- The default threshold is `75` and is defined in the Makefile (`COVERAGE_FAIL_UNDER ?= 75`).
- `make ci-local` calls the same `ci-db-tests` target, so developers see the same coverage failure locally before pushing.
- Ownership: backend maintainers are responsible for keeping this threshold realistic and raising it over time when test coverage improves.

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

## Product/API contract checklist

When your PR changes API-facing code in `app/api/` or `app/schemas/`, complete this checklist:

- [ ] Update `docs/FRONTEND_API_CONTRACT.md`.
- [ ] Bump/refresh the contract version field at the top of `docs/FRONTEND_API_CONTRACT.md`.
- [ ] Add a changelog entry for endpoint or schema changes.
- [ ] If behavior is breaking, document deprecation timeline under the breaking-change rules.
- [ ] Run `make check-contract-sync` (or `make ci-local`) before pushing.

Expected update workflow:

1. Implement API/schema changes.
2. Update `docs/FRONTEND_API_CONTRACT.md` in the same PR.
3. Before commiting, run Ruff lint and format checks locally (`make lint` and `make fmt-check`, or `make ci-local`).
4. Run local checks (`make lint`, `make fmt-check`, `make check-contract-sync`, or `make ci-local`).
5. Push only when Ruff lint and Ruff format checks pass for all commits in the PR.

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
- The change-surface check requires same-PR updates to `Makefile`, `.github/workflows/ci.yml`, `.env.sample`, and relevant docs (`CONTRIBUTING.md` or `docs/*.md`).
- CI also runs `python scripts/check_frontend_contract_sync.py`, which fails if changes under `app/api/` or `app/schemas/` do not include a same-PR update to `docs/FRONTEND_API_CONTRACT.md`.

### Change-surface remediation checklist

If `scripts/check_change_surface.py` fails:

1. Confirm your PR touches one of the guarded surfaces (tests, CI workflow/config, orchestration, or settings).
2. Add/update the synchronized governance files in the same PR:
   - `Makefile`
   - `.github/workflows/ci.yml`
   - `.env.sample`
   - `CONTRIBUTING.md` and/or relevant `docs/*.md`
3. Re-run locally:
   ```bash
   make check-change-surface
   make ci-local
   ```
4. If the surface change was accidental, revert it instead of bypassing the policy.
