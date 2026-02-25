SHELL := /bin/bash

APP_SERVICE ?= api
DEV_ENV_FILE ?= .env.dev
PROD_REQUIRED_ENV_VARS ?= DATABASE_URL AUTH_ISSUER AUTH_JWKS_URL TOKEN_CRYPTO_KMS_KEY_ID

COMPOSE := docker compose
PYTHON ?= python

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
COVERAGE_FAIL_UNDER ?= 75

# Git helpers
GIT_REMOTE ?= origin
GIT_BRANCH ?= main
TAG ?= ci

# Ruff helpers
FIX ?=
RUFF_ARGS ?=

.PHONY: help up down build logs ps sh test test-profile test-search test-discogs-ingestion test-notifications lint fmt fmt-check migrate revision revision-msg downgrade dbshell dbreset migrate-prod prod-up check-prod-env ci-check-migrations test-with-docker-db test-db-up test-db-down test-db-logs test-db-reset check-docker-config ci-local ci-db-tests gh bootstrap-test-deps verify-test-deps test-watch-rules-hard-delete test-background-tasks test-token-security worker-up worker-down worker-logs beat-logs test-celery-tasks typecheck pre-commit-install

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
	@echo ""
	@echo "Testing / CI"
	@echo "  make ci-local              Run full CI flow locally"
	@echo "                             (lint + fmt-check + typecheck + migrate + drift + pytest+coverage)"
	@echo "                             (coverage gate: --cov-fail-under=$(COVERAGE_FAIL_UNDER))"
	@echo "  make test-profile          Run focused profile API tests"
	@echo "  make test-background-tasks Run focused background task transaction test"
	@echo "  make test-discogs-ingestion Run focused Discogs ingestion readiness tests"
	@echo "  make test-token-security   Run token crypto + redaction focused tests"
	@echo "  make test-celery-tasks     Run celery task tests in eager mode (CI-safe)"
	@echo "  make test-with-docker-db   Run tests against test Postgres (manual teardown)"
	@echo "  make check-docker-config   Validate docker compose files render"
	@echo "  make ci-check-migrations   Fail if schema drift detected"
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

# --- Testing ---


typecheck:
	mypy app scripts tests

pre-commit-install:
	pre-commit install
	pre-commit install --hook-type pre-push


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
	$(MAKE) verify-test-deps
	$(PYTHON) -m pytest -q tests/test_watch_rules.py -k hard_delete -rA


test-background-tasks:
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

test-celery-tasks:
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

ci-db-tests:
	@set -euo pipefail; \
	trap '$(COMPOSE) -f $(TEST_DB_COMPOSE) down >/dev/null 2>&1 || true' EXIT; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) up -d $(TEST_DB_SERVICE); \
	$(MAKE) wait-test-db; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "alembic upgrade heads"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "python -m scripts.schema_drift_check"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) $(TEST_APP_SERVICE) "pytest -q --no-cov tests/test_background_tasks.py tests/test_token_crypto_logging.py --disable-warnings --maxfail=1"; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) run --rm -e DATABASE_URL=$(TEST_DATABASE_URL_DOCKER) -e TOKEN_CRYPTO_LOCAL_KEY=$(TEST_TOKEN_CRYPTO_LOCAL_KEY) -e COVERAGE_FILE=/tmp/.coverage $(TEST_APP_SERVICE) "pytest -q --disable-warnings --maxfail=1 --cov-fail-under=$(COVERAGE_FAIL_UNDER)"

# Mirrors the GitHub Actions CI job
ci-local:
	$(MAKE) verify-test-deps; \
	$(MAKE) lint; \
	$(MAKE) fmt-check; \
	$(MAKE) typecheck; \
	$(MAKE) ci-db-tests


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
