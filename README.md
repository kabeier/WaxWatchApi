# WaxWatch API

WaxWatch API powers a "record alert" backend: users define watch rules, the system searches supported marketplaces/providers, stores matching releases/listings, and delivers notifications when new matches are found.

## Purpose

The application provides a backend for:

- User profiles and preferences.
- Watch rule management (`/api/watch-rules`) with query + keyword matching behavior.
- Provider-backed ingestion/search (e.g., Discogs and eBay integrations).
- Event and notification streams for downstream clients.
- Background scheduling/rule execution, including provider request tracking.

In short: it is the core service that turns a user’s "watch this artist/release/keyword" intent into recurring searches and actionable alerts.

## Build stack

The project is a Python 3.12 service with a modern API + worker stack:

- **API framework:** FastAPI + Pydantic (request/response schemas).
- **Server runtime:** Uvicorn.
- **Database:** PostgreSQL via SQLAlchemy, migrations managed with Alembic.
- **Async/background work:** Celery with Redis broker/result backend.
- **Providers:** pluggable provider modules (`app/providers/`) for external marketplace APIs.
- **Quality/tooling:** Ruff (lint/format), mypy (types), pytest (tests/coverage), Docker Compose (local orchestration).

## Large architectural choices

### 1) API and async worker separation

The architecture intentionally splits synchronous HTTP handling (FastAPI) from asynchronous/background execution (Celery workers + beat). This keeps request latency predictable while scheduler/rule-runner/notification flows execute out of band.

### 2) Layered app structure by responsibility

The codebase is organized into stable layers:

- `app/api/routers/`: HTTP endpoints and request contracts.
- `app/schemas/`: API schema models.
- `app/services/`: domain logic (matching, rule runner, scheduler, notifications, ingest).
- `app/providers/`: external provider adapters.
- `app/db/`: persistence models and engine/session primitives.

This separation allows provider logic and domain logic to evolve without coupling endpoint handlers directly to third-party API clients.

### 3) Environment-aware route gating and operational hardening

The service gates dev-only routes by environment, applies global/scoped rate limiting, and uses standardized error envelopes to keep client behavior predictable across validation/HTTP/rate-limit failures.

### 4) Configuration-driven integrations

Provider capability and runtime behavior are controlled by environment configuration, enabling fail-closed production deployments when credentials are missing, while still supporting local/dev workflows through Docker Compose overrides.

### 5) Migration-first persistence discipline

Schema changes are tracked through Alembic migrations, with CI and local commands validating migration + schema drift behavior. This keeps database evolution explicit and safer for production rollouts.

## Local development quick start

```bash
# Start API + Redis + Postgres (dev override)
make up

# Run database migrations
make migrate

# Run quality gates required for contributions
make lint
make fmt-check
```

Open API docs at `http://localhost:8000/docs` once the API is running.
