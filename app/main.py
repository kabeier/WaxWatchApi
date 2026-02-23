# app/main.py
from __future__ import annotations

from fastapi import FastAPI

from app.api.middleware import RequestIDMiddleware

# dev routers
from app.api.routers.dev_ingest import router as dev_ingest_router
from app.api.routers.dev_runner import router as dev_runner_router
from app.api.routers.events import router as events_router
from app.api.routers.health import router as health_router
from app.api.routers.provider_requests import router as provider_requests_router
from app.api.routers.watch_rules import router as watch_rules_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)

    logger.info(
        "app.startup",
        extra={
            "app_name": settings.app_name,
            "environment": settings.environment,
            "json_logs": settings.json_logs,
            "auth_issuer_configured": bool(settings.auth_issuer or settings.supabase_url),
            "auth_jwks_url_configured": bool(settings.auth_jwks_url or settings.supabase_url),
        },
    )

    app = FastAPI(title=settings.app_name)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health_router)
    app.include_router(events_router, prefix="/api")
    app.include_router(provider_requests_router, prefix="/api")
    app.include_router(watch_rules_router, prefix="/api")

    if settings.environment.lower() != "prod":
        logger.info("dev_routes.enabled", extra={"environment": settings.environment})
        app.include_router(dev_ingest_router, prefix="/api")
        app.include_router(dev_runner_router, prefix="/api")
    else:
        logger.info("dev_routes.disabled", extra={"environment": settings.environment})

    return app


app = create_app()
