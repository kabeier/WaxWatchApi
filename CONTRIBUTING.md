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
- The same script also enforces policy synchronization when new `Settings` fields, Make targets, or CI run commands are introduced.
- If these changes are intentional, include explicit updates to the files above so the policy check can pass.
