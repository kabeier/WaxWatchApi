# Deployment Workflow (Runtime-Injected Secrets)

This project uses **runtime-injected environment variables** for production.

- Do **not** rely on checked-in or server-local `.env` files for production.
- Inject secrets via your CI/CD platform or secret manager (GitHub Actions secrets, AWS/GCP secret managers, Vault, etc.).
- Keep `.env.sample` as a local/dev reference only.

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

`make migrate-prod` and `make prod-up` now consume the current process environment (runtime injection), not `--env-file .env.prod`.

If your deployment needs a different required set, override `PROD_REQUIRED_ENV_VARS`:

```bash
make PROD_REQUIRED_ENV_VARS="DATABASE_URL AUTH_ISSUER AUTH_JWKS_URL TOKEN_CRYPTO_KMS_KEY_ID" check-prod-env
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
