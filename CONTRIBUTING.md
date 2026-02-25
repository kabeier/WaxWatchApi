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
- Pytest with coverage collection and threshold enforcement from `pytest.ini`

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
