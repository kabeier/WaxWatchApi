# Repository agent workflow requirements

All human and agent contributors must run the Ruff quality gates before considering any code change complete:

1. `make lint`
2. `make fmt-check`

If either command fails, use the remediation path and re-run the checks:

- `make lint FIX=1` to apply auto-fixable Ruff lint changes.
- `make fmt` to apply Ruff formatting.

Pre-commit hardening is strongly recommended:

- Run `make pre-commit-install` to install both pre-commit and pre-push hooks.
- Hooks enforce `ruff check .` and `ruff format --check .` locally before code is shared.
