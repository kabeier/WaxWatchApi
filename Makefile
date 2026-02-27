SHELL := /bin/bash

# Governance note: notification enqueue semantics are post-commit; keep CI/.env.sample/docs/CHANGELOG synchronized when task orchestration changes.

APP_SERVICE ?= api
DEV_ENV_FILE ?= .env.dev
PROD_REQUIRED_ENV_VARS ?= DATABASE_URL AUTH_ISSUER AUTH_JWKS_URL TOKEN_CRYPTO_KMS_KEY_ID DISCOGS_USER_AGENT DISCOGS_TOKEN EBAY_CLIENT_ID EBAY_CLIENT_SECRET

COMPOSE := docker compose
PYTHON ?= python
LOCK_PYTHON ?= python3.12
LOCK_HEADER_PYTHON ?= 3.12

TEST_DB_COMPOSE ?= docker-compose.test.yml
TEST_DB_SERVICE ?= postgres
TEST_DATABASE_URL ?= postgresql+psycopg://waxwatch:waxwatch@localhost:5433/waxwatch_test
TEST_DATABASE_URL_DOCKER ?= postgresql+psycopg://waxwatch:waxwatch@postgres:5432/waxwatch_test
TEST_APP_SERVICE ?= api-test
TEST_AUTH_ISSUER ?= http://127.0.0.1:8765/auth/v1
TEST_AUTH_AUDIENCE ?= authenticated
TEST_AUTH_JWKS_URL ?= http://127.0.0.1:8765/auth/v1/.well-known/jwks.json
TEST_AUTH_JWT_ALGORITHMS ?= ["RS256"]
TEST_AUTH_JWKS_CACHE_TTL_SECONDS ?= 300
TEST_AUTH_CLOCK_SKEW_SECONDS ?= 0
TEST_TOKEN_CRYPTO_LOCAL_KEY ?= 5pq6kEUS_UIk1_4qatN-Lx42s3e362VNq5CgyI4LAZU=
COVERAGE_FAIL_UNDER ?= 85

# Git helpers
GIT_REMOTE ?= origin
GIT_BRANCH ?= main
TAG ?= ci

# Governance note: when CI/security workflow action references are refreshed,
# keep this file, .env.sample, CHANGELOG.md, and CONTRIBUTING.md updated together
# so check-change-surface/check-policy-sync can validate synchronized intent.
# Token lifecycle normalization/backfill behavior is schema/service-driven; no new runtime env knobs were added.
# Change-surface note: token lifecycle migration test changes still require governance/doc/changelog sync updates.
# Policy sync marker: keep governance artifacts in lockstep for token lifecycle migration test-path edits.
# Policy sync marker: migration scope normalization CTE/test updates require governance+docs+changelog sync.
# Policy sync marker: lifecycle migration test edits must account for SQL NULL vs JSONB null behavior and sync governance docs.
# Provider registry governance note: default search provider resolution excludes mock outside dev/test/local safe environments.
# Ruff helpers
FIX ?=
RUFF_ARGS ?=

.PHONY: help up down build logs ps sh test test-profile test-search test-discogs-ingestion test-notifications lint fmt fmt-check migrate revision revision-msg downgrade dbshell dbreset migrate-prod prod-up check-prod-env ci-check-migrations test-with-docker-db test-db-up test-db-down test-db-logs test-db-reset check-docker-config check-policy-sync check-compose-secret-defaults check-smoke-workflow-config check-change-surface check-contract-sync check-openapi-snapshot openapi-snapshot check-coverage-regression ci-static-checks ci-local ci-db-tests gh bootstrap-test-deps verify-test-deps test-watch-rules-hard-delete test-background-tasks test-token-security test-rate-limit worker-up worker-down worker-logs beat-logs test-celery-tasks test-matching test-coverage-uplift typecheck pre-commit-install perf-smoke lock-refresh ci-celery-redis-smoke wait-test-redis check-lock-python-version security-deps-audit security-secrets-scan

help:
	@echo ""
	@echo "WaxWatch / RecordAlert — Command Reference"
	@echo "------------------------------------------------------------"
	@echo ""
	@echo "Docker (Dev Environment)"
	@echo "  make up                    Start dev stack (builds if needed)"
	@echo "  make down                  Stop containers"
	@echo "  make build                 Rebuild images"
	@echo "  make logs                  Follow API logs"
	@echo "  make ps                    Show running services"
	@echo "  make sh                    Shell inside API container"
	@echo "  make worker-up             Start celery worker + beat"
	@echo "  make worker-down           Stop celery worker + beat"
	@echo "  make worker-logs           Follow celery worker logs"
	@echo ""
	@echo "Database (Dev / Local Docker DB)"
	@echo "  make migrate               Apply migrations (upgrade head)"
	@echo "  make revision MSG='...'    Create autogen Alembic revision"
	@echo "  make revision-msg MSG='...' Create empty Alembic revision"
	@echo "  make downgrade REV=-1      Downgrade migration"
	@echo "  make dbshell               Open psql shell"
	@echo "  make dbreset               Print instructions to remove DB volume"
	@echo ""
	@echo "Code Quality"
	@echo "  make lint                  Run ruff lint"
	@echo "  make lint FIX=1            Run ruff with auto-fix"
	@echo "  make lint RUFF_ARGS='...'  Pass extra args to ruff"
	@echo "  make fmt                   Auto-format code"
	@echo "  make fmt-check             Fail if formatting differs"
	@echo "  make typecheck             Run mypy static type checks"
	@echo "  make pre-commit-install    Install pre-commit hooks (pre-commit + pre-push)"
	@echo "  make lock-refresh          Rebuild requirements*.txt from requirements*.in using Python 3.12"
	@echo "  make check-lock-python-version Fail if lockfiles were not generated with Python 3.12"
	@echo ""
	@echo "Testing / CI"
	@echo "  make ci-local              Run full CI flow locally"
	@echo "                             (lint + fmt-check + typecheck + migrate + drift + pytest+coverage)"
	@echo "                             (coverage gate: --cov-fail-under=$(COVERAGE_FAIL_UNDER))"
	@echo "  make test-profile          Run focused profile API tests (local debugging only; non-authoritative)"
	@echo "  make test-background-tasks Run focused background task transaction test (local debugging only; non-authoritative)"
	@echo "  make test-discogs-ingestion Run focused Discogs ingestion readiness tests (local debugging only; non-authoritative)"
	@echo "  make test-token-security   Run token crypto + redaction focused tests (local debugging only; non-authoritative)"
	@echo "  make test-celery-tasks     Run celery task tests in eager mode (local debugging only; non-authoritative)"
	@echo "  make ci-celery-redis-smoke Run Redis-backed non-eager Celery smoke integration test"
	@echo "  make test-matching         Run Discogs listing-matching focused tests (local debugging only; non-authoritative)"
	@echo "  make test-coverage-uplift  Run focused coverage-uplift test modules (local debugging only; non-authoritative)"
	@echo "  make test-with-docker-db   Run tests against test Postgres (manual teardown)"
	@echo "  make check-docker-config   Validate docker compose files render"
	@echo "  make check-compose-secret-defaults Validate fail-closed secret default policy in compose"
	@echo "  make check-policy-sync     Validate .env.sample + governance sync policy (change-surface/changelog + CI concurrency/docs + action pinning sync)"
	@echo "                             Includes Settings/.env governance sync for runtime knobs (for example RATE_LIMIT_* fields)."
	@echo "  make check-change-surface  Validate integration hygiene change-surface policy"
	@echo "  make check-contract-sync   Validate API-facing changes update frontend contract doc"
	@echo "  make check-openapi-snapshot Fail if generated OpenAPI schema differs from docs/openapi.snapshot.json"
	@echo "  make openapi-snapshot      Regenerate docs/openapi.snapshot.json from app/main.py"
	@echo "  make ci-check-migrations   Fail if schema drift detected"
	@echo "  make perf-smoke            Run k6 core-flow perf smoke harness (local/staging/GHA smoke workflow)"
	@echo "                             Release gate workflow: .github/workflows/release-gates.yml"
	@echo "  make security-deps-audit   Run local pip-audit against requirements*.in/txt"
	@echo "  make security-secrets-scan Run local gitleaks repository scan (if installed)"
	@echo ""
	@echo "Git / Release Workflow"
	@echo "  make gh MSG='...'          Run ci-local, then commit & push if successful"
	@echo ""
	@echo "Production"
	@echo "  make check-prod-env        Fail if required runtime prod env vars are missing"
	@echo "  make migrate-prod          Run migrations using runtime-injected prod secrets"
	@echo "  make prod-up               Start production compose stack with runtime-injected secrets"
	@echo ""
up:
	$(COMPOSE) --env-file $(DEV_ENV_FILE) up --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f $(APP_SERVICE)

ps:
	$(COMPOSE) ps

sh:
	$(COMPOSE) exec $(APP_SERVICE) bash


worker-up:
	$(COMPOSE) up -d worker beat redis

worker-down:
	$(COMPOSE) stop worker beat

worker-logs:
	$(COMPOSE) logs -f worker

beat-logs:
	$(COMPOSE) logs -f beat

# --- Code quality ---
lint:
	ruff check $(if $(FIX),--fix,) $(RUFF_ARGS) .

fmt:
	ruff format .

fmt-check:
	ruff format --check .

lock-refresh:
	$(LOCK_PYTHON) -m piptools compile --output-file=requirements.txt requirements.in
	$(LOCK_PYTHON) -m piptools compile --output-file=requirements-dev.txt requirements-dev.in

check-lock-python-version:
	@for lockfile in requirements.txt requirements-dev.txt; do \
		if ! grep -q "autogenerated by pip-compile with Python $(LOCK_HEADER_PYTHON)" "$$lockfile"; then \
			echo "error: $$lockfile must be regenerated with Python $(LOCK_HEADER_PYTHON) (run: make lock-refresh)"; \
			exit 1; \
		fi; \
	done

# --- Testing ---


typecheck:
	mypy app scripts tests

pre-commit-install:
	pre-commit install
	pre-commit install --hook-type pre-push

perf-smoke:
	@# SLO gate: scripts/perf/core_flows_smoke.js fails on p95/p99/error/check-rate threshold breaches.
	@# Observability note: metrics scrape includes DB pool utilization telemetry for saturation dashboards.
	@# Test coverage note: keep health metrics branch coverage in sync with scrape-time pool utilization guards.
	@if [ -z "$$PERF_BASE_URL" ] || [ -z "$$PERF_BEARER_TOKEN" ]; then 		echo "error: PERF_BASE_URL and PERF_BEARER_TOKEN are required"; 		echo "example: PERF_BASE_URL=http://127.0.0.1:8000 PERF_BEARER_TOKEN='<jwt>' PERF_RULE_ID='<uuid>' make perf-smoke"; 		exit 1; 	fi
	@if command -v k6 >/dev/null 2>&1; then 		echo "Using local k6 binary"; 		k6 run scripts/perf/core_flows_smoke.js; 	else 		echo "k6 not found; using grafana/k6 Docker image"; 		docker run --rm -i 			-e PERF_BASE_URL -e PERF_BEARER_TOKEN -e PERF_RULE_ID -e PERF_ENABLE_RULE_RUN 			-e PERF_VUS -e PERF_DURATION -e PERF_LIST_PATH -e PERF_RELEASES_LIST_PATH -e PERF_SEARCH_PATH 			-e PERF_RULE_RUN_PATH -e PERF_SEARCH_KEYWORDS -e PERF_SEARCH_PROVIDERS -e PERF_SEARCH_PAGE 			-e PERF_SEARCH_PAGE_SIZE 			-v "$(PWD):/work" -w /work 			grafana/k6:0.52.0 run scripts/perf/core_flows_smoke.js; 	fi

security-deps-audit:
	@set -euo pipefail; 	mapfile -t dep_files < <(find . -type f \( -name 'requirements*.txt' -o -name 'requirements*.in' \) | sort); 	if [ "$${#dep_files[@]}" -eq 0 ]; then 		echo "No requirements*.txt or requirements*.in files found; skipping audit."; 		exit 0; 	fi; 	$(PYTHON) -m pip install --upgrade pip pip-audit >/dev/null; 	for dep_file in "$${dep_files[@]}"; do 		echo "Auditing $${dep_file}"; 		$(PYTHON) -m pip_audit -r "$${dep_file}"; 	done

security-secrets-scan:
	@if ! command -v gitleaks >/dev/null 2>&1; then 		echo "error: gitleaks is not installed. Install from https://github.com/gitleaks/gitleaks/releases"; 		exit 1; 	fi
	gitleaks detect --source . --verbose


# Installs the local Python test toolchain (includes PyJWT/cryptography used in tests/conftest.py)
bootstrap-test-deps:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements-dev.txt

verify-test-deps:
	$(PYTHON) -c "import sys, jwt, cryptography; print(f'ok: jwt+cryptography available on {sys.executable}')"

test-db-up:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) up -d $(TEST_DB_SERVICE)

test-db-down:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) down

test-db-logs:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) logs -f $(TEST_DB_SERVICE)

test-db-reset:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) down -v

test-with-docker-db: test-db-up
	$(MAKE) wait-test-db
	$(MAKE) verify-test-deps
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "alembic upgrade head"
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "python -m scripts.schema_drift_check"
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "pytest -q -rA"

test-discogs-ingestion:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_discogs_retry.py tests/test_discogs_integration_router.py tests/test_ebay_provider.py tests/test_ebay_affiliate.py tests/test_rule_runner_provider_logging.py tests/test_scheduler.py tests/test_provider_requests_router.py tests/test_token_crypto_logging.py -rA


test-notifications:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_notifications.py -rA

test-profile:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_profile_router.py -rA


test-search:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_search_router.py -rA


test-watch-rules-hard-delete:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	$(MAKE) verify-test-deps
	$(PYTHON) -m pytest -q tests/test_watch_rules.py -k hard_delete -rA


test-background-tasks:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_background_tasks.py -rA

test-token-security:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_token_crypto_logging.py tests/test_discogs_integration_router.py -rA



test-rate-limit:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m alembic upgrade heads
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	timeout 240s $(PYTHON) -m pytest --no-cov -vv -s --maxfail=1 tests/test_rate_limit.py -rA
test-matching:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_matching.py -rA

test-coverage-uplift:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	EBAY_CLIENT_ID=test-ebay-client-id \
	EBAY_CLIENT_SECRET=test-ebay-client-secret \
	EBAY_CAMPAIGN_ID=1234567890 \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	$(PYTHON) -m pytest -q tests/test_watch_rules.py tests/test_notifications.py tests/test_tasks_unit.py tests/test_email_provider.py tests/test_search_service.py tests/test_db_base.py -rA

test-celery-tasks:
	# Local debugging helper only (non-authoritative for CI pass/fail).
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	AUTH_ISSUER=$(TEST_AUTH_ISSUER) \
	AUTH_AUDIENCE=$(TEST_AUTH_AUDIENCE) \
	AUTH_JWKS_URL=$(TEST_AUTH_JWKS_URL) \
	AUTH_JWT_ALGORITHMS='$(TEST_AUTH_JWT_ALGORITHMS)' \
	AUTH_JWKS_CACHE_TTL_SECONDS=$(TEST_AUTH_JWKS_CACHE_TTL_SECONDS) \
	AUTH_CLOCK_SKEW_SECONDS=$(TEST_AUTH_CLOCK_SKEW_SECONDS) \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) \
	CELERY_TASK_ALWAYS_EAGER=true \
	CELERY_TASK_EAGER_PROPAGATES=true \
	$(PYTHON) -m pytest -q tests/test_celery_tasks.py -rA

check-docker-config:
	DATABASE_URL=postgresql+psycopg://waxwatch:waxwatch@db:5432/waxwatch \
	DISCOGS_USER_AGENT=waxwatch-config-check \
	DISCOGS_TOKEN=waxwatch-config-check \
	$(COMPOSE) -f docker-compose.yml config >/dev/null
	DATABASE_URL=postgresql+psycopg://waxwatch:waxwatch@db:5432/waxwatch \
	DISCOGS_USER_AGENT=waxwatch-config-check \
	DISCOGS_TOKEN=waxwatch-config-check \
	$(COMPOSE) -f docker-compose.yml -f docker-compose.override.yml config >/dev/null
	$(COMPOSE) -f docker-compose.test.yml config >/dev/null

check-policy-sync:
	$(PYTHON) scripts/check_env_sample.py
	$(MAKE) check-compose-secret-defaults
	$(MAKE) check-smoke-workflow-config
	$(MAKE) check-change-surface

check-smoke-workflow-config:
	@set -euo pipefail; \
	test -f .github/workflows/smoke.yml; \
	grep -q "perf_base_url:" .github/workflows/smoke.yml; \
	grep -q "perf_rule_id:" .github/workflows/smoke.yml; \
	grep -q "PERF_BASE_URL source:" .github/workflows/smoke.yml; \
	grep -q "scheduler_lag_p95_seconds:" .github/workflows/release-gates.yml; \
	grep -q "queue_lag_p99_seconds:" .github/workflows/release-gates.yml; \
	echo "ok: smoke workflow dispatch/fallback diagnostics are present"

check-compose-secret-defaults:
	$(PYTHON) scripts/check_compose_secret_defaults.py

check-change-surface:
	# Keep governance files/docs synchronized whenever integration surfaces (tests/CI/settings/task orchestration) change.
	$(PYTHON) scripts/check_change_surface.py

check-contract-sync:
	$(PYTHON) scripts/check_frontend_contract_sync.py

check-openapi-snapshot:
	$(PYTHON) -m scripts.openapi_snapshot --check

openapi-snapshot:
	$(PYTHON) -m scripts.openapi_snapshot --update

check-coverage-regression:
	$(PYTHON) scripts/check_coverage_regression.py

wait-test-redis:
	@set -euo pipefail; \
	echo "Waiting for Redis test service ..."; \
	for i in $$(seq 1 60); do \
		if $(COMPOSE) -f $(TEST_DB_COMPOSE) exec -T redis redis-cli ping >/dev/null 2>&1; then \
			echo "Redis is ready."; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Redis did not become ready in time. Showing logs:"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) logs --no-color redis | tail -n 200; \
	exit 1

ci-celery-redis-smoke:
	@set -euo pipefail; \
	trap '$(COMPOSE) -f $(TEST_DB_COMPOSE) down >/dev/null 2>&1 || true' EXIT; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) up -d $(TEST_DB_SERVICE) redis; \
	$(MAKE) wait-test-db; \
	$(MAKE) wait-test-redis; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "alembic upgrade heads"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) -e CELERY_TASK_ALWAYS_EAGER=false -e CELERY_TASK_EAGER_PROPAGATES=true -e RUN_CELERY_REDIS_INTEGRATION=1 $(TEST_APP_SERVICE) "bash scripts/ci_celery_redis_smoke.sh"
wait-test-db:
	@set -euo pipefail; \
	echo "Waiting for Postgres (container + host port) ..."; \
	for i in $$(seq 1 60); do \
		if $(COMPOSE) -f $(TEST_DB_COMPOSE) exec -T $(TEST_DB_SERVICE) pg_isready -U waxwatch -d waxwatch_test >/dev/null 2>&1; then \
			if PGPASSWORD=waxwatch psql "host=127.0.0.1 port=5433 user=waxwatch dbname=waxwatch_test sslmode=disable" -c "select 1" >/dev/null 2>&1; then \
				echo "Postgres is ready (container + host)."; \
				exit 0; \
			fi; \
		fi; \
		sleep 1; \
	done; \
	echo "Postgres did not become ready in time. Showing logs:"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) logs --no-color $(TEST_DB_SERVICE) | tail -n 200; \
	exit 1

# CI contract:
# - ci-local is the canonical CI entrypoint for both local and GitHub Actions runs.
# - Keep static governance checks in ci-static-checks (used by both ci-local and CI static-checks job).
# - Keep ci-local wired as ci-static-checks + ci-db-tests + ci-celery-redis-smoke.
# - Keep migration upgrade + schema drift checks + default pytest discovery with coverage in ci-db-tests.
# - Worker-dependent integration tests must not rely on implicit worker presence in ci-db-tests.
# - ci-db-tests intentionally excludes integration-marked tests (-m "not integration") and also ignores
#   tests/test_celery_redis_integration.py as a belt-and-suspenders guard against worker-dependent leakage.
# - ci-celery-redis-smoke readiness is checked by scripts/ci_celery_redis_smoke.sh via worker PID + logs (no inspect ping).
ci-static-checks:
	$(MAKE) verify-test-deps; \
	$(MAKE) check-docker-config; \
	$(MAKE) check-policy-sync; \
	$(MAKE) check-contract-sync; \
	$(MAKE) check-openapi-snapshot; \
	$(MAKE) lint; \
	$(MAKE) fmt-check; \
	$(MAKE) typecheck

ci-db-tests:
	@set -euo pipefail; \
	trap '$(COMPOSE) -f $(TEST_DB_COMPOSE) down >/dev/null 2>&1 || true' EXIT; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) up -d $(TEST_DB_SERVICE); \
	$(MAKE) wait-test-db; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "alembic upgrade heads"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "python -m scripts.schema_drift_check"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) -e COVERAGE_FILE=/tmp/.coverage $(TEST_APP_SERVICE) "pytest -q --disable-warnings --maxfail=1 -m 'not integration' --cov-fail-under=$(COVERAGE_FAIL_UNDER) --ignore=tests/test_celery_redis_integration.py"

# Mirrors the GitHub Actions CI job
ci-local:
	$(MAKE) ci-static-checks; \
	$(MAKE) ci-db-tests; \
	$(MAKE) ci-celery-redis-smoke


gh: ci-local
	@if [ -z "$(MSG)" ]; then echo "MSG is required. Example: make gh MSG='fix schema drift'"; exit 1; fi
	@set -euo pipefail; \
	# if nothing changed (tracked or untracked), bail
	if git diff --quiet && git diff --cached --quiet && [ -z "$$(git ls-files --others --exclude-standard)" ]; then \
		echo "Working tree clean — nothing to commit."; \
		exit 0; \
	fi; \
	git add -A; \
	git commit -m "$(MSG)"; \
	git push $(GIT_REMOTE) $(GIT_BRANCH)
	
# --- Alembic (dev/local db) ---
migrate:
	$(COMPOSE) --env-file $(DEV_ENV_FILE) exec $(APP_SERVICE) alembic upgrade head

revision:
	@if [ -z "$(MSG)" ]; then echo "MSG is required. Example: make revision MSG='add listings table'"; exit 1; fi
	$(COMPOSE) --env-file $(DEV_ENV_FILE) exec $(APP_SERVICE) alembic revision --autogenerate -m "$(MSG)"

revision-msg:
	@if [ -z "$(MSG)" ]; then echo "MSG is required. Example: make revision-msg MSG='empty revision'"; exit 1; fi
	$(COMPOSE) --env-file $(DEV_ENV_FILE) exec $(APP_SERVICE) alembic revision -m "$(MSG)"

downgrade:
	@if [ -z "$(REV)" ]; then echo "REV is required. Example: make downgrade REV=-1"; exit 1; fi
	$(COMPOSE) --env-file $(DEV_ENV_FILE) exec $(APP_SERVICE) alembic downgrade $(REV)

dbshell:
	$(COMPOSE) exec db psql -U waxwatch -d waxwatch

dbreset:
	@echo "This will delete the local postgres volume waxwatch_pgdata."
	@echo "Run: docker volume rm $$(docker volume ls -q | grep waxwatch_pgdata)"
	@exit 1

# --- Migration drift check (NO revision files) ---
ci-check-migrations:
	$(COMPOSE) --env-file $(DEV_ENV_FILE) exec $(APP_SERVICE) python -m scripts.schema_drift_check

# --- Prod migrations / run ---
check-prod-env:
	@set -euo pipefail; \
	missing=""; \
	for var in $(PROD_REQUIRED_ENV_VARS); do \
		if [ -z "$${!var:-}" ]; then \
			missing="$$missing $$var"; \
		fi; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "Missing required production env vars/secrets:$$missing"; \
		echo "Inject them at runtime from CI/CD secrets or your secret manager before running production targets."; \
		exit 1; \
	fi; \
	echo "Production env check passed."

migrate-prod: check-prod-env
	$(COMPOSE) run --rm $(APP_SERVICE) alembic upgrade head

prod-up: check-prod-env
	$(COMPOSE) -f docker-compose.yml up --build
