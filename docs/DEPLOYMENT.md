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
8. Observability checks completed:
   - SLO dashboards are reporting (API latency by endpoint category, provider error budgets, scheduler freshness, notification lag).
   - Alert thresholds match `docs/OPERATIONS_OBSERVABILITY.md` numeric warning/critical targets.

## Change synchronization requirement

When introducing new environment variables, CI/test commands, or Make targets, update `.env.sample`, `Makefile`, `.github/workflows/ci.yml`, and `CONTRIBUTING.md` in the same PR, plus any affected docs.
CI enforces this through `python scripts/check_change_surface.py` and `python scripts/check_env_sample.py` in the workflow.
