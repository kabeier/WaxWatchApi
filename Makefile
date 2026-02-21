SHELL := /usr/bin/env bash

APP_SERVICE := api
DEV_ENV_FILE := .env
PROD_ENV_FILE := .env.prod

.PHONY: help up down build logs ps sh test lint fmt \
        dbshell dbreset \
        migrate migrate-prod revision revision-msg downgrade \
        prod-up prod-logs

help:
	@echo ""
	@echo "WaxWatch / RecordAlert - common commands"
	@echo ""
	@echo "Docker:"
	@echo "  make up            - dev up (uses docker-compose.override.yml automatically)"
	@echo "  make down          - stop containers"
	@echo "  make build         - rebuild images"
	@echo "  make logs          - follow api logs"
	@echo "  make ps            - show running services"
	@echo "  make sh            - shell inside api container"
	@echo ""
	@echo "Database:"
	@echo "  make migrate       - alembic upgrade head (dev/local docker db)"
	@echo "  make revision MSG='...' - create alembic revision (autogenerate)"
	@echo "  make downgrade REV=-1   - downgrade (e.g. -1 or <revision_id>)"
	@echo "  make dbshell       - psql into local docker db"
	@echo "  make dbreset       - WARNING: nukes local docker db volume"
	@echo ""
	@echo "Prod-ish (uses .env.prod):"
	@echo "  make migrate-prod  - alembic upgrade head against prod DB (Supabase)"
	@echo "  make prod-up       - run api using docker-compose.yml + .env.prod"
	@echo ""

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f $(APP_SERVICE)

ps:
	docker compose ps

sh:
	docker compose exec $(APP_SERVICE) bash

# --- migrations (dev/local) ---

migrate:
	docker compose exec $(APP_SERVICE) alembic upgrade head

revision:
	@if [ -z "$(MSG)" ]; then echo "MSG is required. Example: make revision MSG='add listings table'"; exit 1; fi
	docker compose exec $(APP_SERVICE) alembic revision --autogenerate -m "$(MSG)"

# revision without autogenerate:
revision-msg:
	@if [ -z "$(MSG)" ]; then echo "MSG is required. Example: make revision-msg MSG='empty revision'"; exit 1; fi
	docker compose exec $(APP_SERVICE) alembic revision -m "$(MSG)"

downgrade:
	@if [ -z "$(REV)" ]; then echo "REV is required. Example: make downgrade REV=-1"; exit 1; fi
	docker compose exec $(APP_SERVICE) alembic downgrade $(REV)

# --- prod migrations (Supabase/etc) ---

migrate-prod:
	@if [ ! -f "$(PROD_ENV_FILE)" ]; then echo "$(PROD_ENV_FILE) not found"; exit 1; fi
	docker compose --env-file $(PROD_ENV_FILE) run --rm $(APP_SERVICE) alembic upgrade head

# --- db helpers (local docker) ---

dbshell:
	docker compose exec db psql -U waxwatch -d waxwatch

dbreset:
	@echo "This will DELETE local Postgres volume waxwatch_pgdata."
	@echo "Ctrl+C to cancel, or press Enter to continue."
	@read
	docker compose down -v
	docker volume rm -f $$(docker volume ls -q | grep waxwatch_pgdata || true) || true

# --- prod run locally (no override) ---

prod-up:
	@if [ ! -f "$(PROD_ENV_FILE)" ]; then echo "$(PROD_ENV_FILE) not found"; exit 1; fi
	docker compose --env-file $(PROD_ENV_FILE) -f docker-compose.yml up --build

prod-logs:
	@if [ ! -f "$(PROD_ENV_FILE)" ]; then echo "$(PROD_ENV_FILE) not found"; exit 1; fi
	docker compose --env-file $(PROD_ENV_FILE) -f docker-compose.yml logs -f $(APP_SERVICE)