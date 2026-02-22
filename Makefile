SHELL := /bin/bash

APP_SERVICE ?= api
DEV_ENV_FILE ?= .env.dev
PROD_ENV_FILE ?= .env.prod

COMPOSE := docker compose

TEST_DB_COMPOSE ?= docker-compose.test.yml
TEST_DB_SERVICE ?= postgres
TEST_DATABASE_URL ?= postgresql+psycopg://waxwatch:waxwatch@localhost:5433/waxwatch_test

# Git helpers
GIT_REMOTE ?= origin
GIT_BRANCH ?= main
TAG ?= ci

# Ruff helpers
FIX ?=
RUFF_ARGS ?=

.PHONY: help up down build logs ps sh test lint fmt fmt-check migrate revision revision-msg downgrade dbshell dbreset migrate-prod prod-up ci-check-migrations test-with-docker-db test-db-up test-db-down test-db-logs test-db-reset ci-local gh

help:
	@echo ""
	@echo "WaxWatch / RecordAlert - common commands"
	@echo ""
	@echo "Docker:"
	@echo "  make up                  - dev up (uses docker-compose.override.yml automatically)"
	@echo "  make down                - stop containers"
	@echo "  make build               - rebuild images"
	@echo "  make logs                - follow api logs"
	@echo "  make ps                  - show running services"
	@echo "  make sh                  - shell inside api container"
	@echo ""
	@echo "Database (Dev / Local Docker DB):"
	@echo "  make migrate             - alembic upgrade head (dev/local docker db)"
	@echo "  make revision MSG='...'  - create alembic revision (autogenerate)"
	@echo "  make revision-msg MSG='...' - create empty alembic revision"
	@echo "  make downgrade REV=-1    - downgrade (e.g. -1 or <revision_id>)"
	@echo "  make dbshell             - psql into local docker db"
	@echo "  make dbreset             - WARNING: nukes local docker db volume"
	@echo ""
	@echo "Testing & Code Quality:"
	@echo "  make lint [FIX=1] [RUFF_ARGS='...'] - ruff lint (optional auto-fix)"
	@echo "  make fmt                 - ruff format (writes changes)"
	@echo "  make fmt-check           - ruff format --check"
	@echo ""
	@echo "  make ci-local            - run CI steps locally (lint + fmt-check + migrate + drift + pytest)"
	@echo "  make gh MSG='...' [TAG='ci'] - run ci-local, then commit+push if it passes"
	@echo ""
	@echo "  make ci-check-migrations - fail if models != DB schema (no new revision files)"
	@echo "  make test-with-docker-db - spin up test Postgres, migrate, drift-check, run pytest (does NOT auto-down)"
	@echo "  make test-db-up          - start test Postgres"
	@echo "  make test-db-down        - stop test Postgres"
	@echo ""
	@echo "Prod-ish (no .env in compose; uses env vars):"
	@echo "  make migrate-prod        - alembic upgrade head against prod DB (uses --env-file .env.prod)"
	@echo "  make prod-up             - run api using docker-compose.yml + --env-file .env.prod"
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

# --- Code quality ---
lint:
	ruff check $(if $(FIX),--fix,) $(RUFF_ARGS) .

fmt:
	ruff format .

fmt-check:
	ruff format --check .

# --- Testing ---

test-db-up:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) up -d $(TEST_DB_SERVICE)

test-db-down:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) down

test-db-logs:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) logs -f $(TEST_DB_SERVICE)

test-db-reset:
	$(COMPOSE) -f $(TEST_DB_COMPOSE) down -v

test-with-docker-db: test-db-up
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	alembic upgrade head
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	python -m scripts.schema_drift_check
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	DISCOGS_USER_AGENT=test-agent \
	DISCOGS_TOKEN=test-token \
	pytest -q -rA

# Mirrors the GitHub Actions CI job, but uses your dockerized test Postgres.
# Ensures the test DB is torn down even if a step fails.
ci-local:
	@set -euo pipefail; \
	trap '$(COMPOSE) -f $(TEST_DB_COMPOSE) down >/dev/null 2>&1 || true' EXIT; \
	$(COMPOSE) -f $(TEST_DB_COMPOSE) up -d $(TEST_DB_SERVICE); \
	ruff check .; \
	ruff format --check .; \
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	DISCOGS_USER_AGENT=waxwatch-ci \
	DISCOGS_TOKEN=ci-token \
	alembic upgrade head; \
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	DISCOGS_USER_AGENT=waxwatch-ci \
	DISCOGS_TOKEN=ci-token \
	python -m scripts.schema_drift_check; \
	ENVIRONMENT=test \
	LOG_LEVEL=INFO \
	JSON_LOGS=false \
	DATABASE_URL=$(TEST_DATABASE_URL) \
	DB_POOL=queue \
	DB_POOL_SIZE=5 \
	DB_MAX_OVERFLOW=10 \
	DISCOGS_USER_AGENT=waxwatch-ci \
	DISCOGS_TOKEN=ci-token \
	pytest -q --disable-warnings --maxfail=1

# Run CI locally, then commit+push if it passes.

gh: ci-local
	@if [ -z "$(MSG)" ]; then echo "MSG is required. Example: make gh MSG='fix schema drift' TAG='api'"; exit 1; fi
	@set -euo pipefail; \
	if [ -z "$$(git status --porcelain)" ]; then \
		echo "Working tree clean — nothing to commit."; \
		exit 0; \
	fi; \
	git add -A; \
	git commit -m "[$(TAG)] $(MSG)"; \
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
migrate-prod:
	@if [ ! -f "$(PROD_ENV_FILE)" ]; then echo "$(PROD_ENV_FILE) not found"; exit 1; fi
	$(COMPOSE) --env-file $(PROD_ENV_FILE) run --rm $(APP_SERVICE) alembic upgrade head

prod-up:
	@if [ ! -f "$(PROD_ENV_FILE)" ]; then echo "$(PROD_ENV_FILE) not found"; exit 1; fi
	$(COMPOSE) --env-file $(PROD_ENV_FILE) -f docker-compose.yml up --build