from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.api.middleware import RequestIDMiddleware

from app.api.routers.health import router as health_router
from app.api.routers.watch_rules import router as watch_rules_router
from app.api.routers.events import router as events_router
from app.api.routers.dev_ingest import router as dev_ingest_router
from app.api.routers.dev_runner import router as dev_runner_router
from app.api.routers.provider_requests import router as provider_requests_router


def create_app() -> FastAPI:
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)
    logger = get_logger(__name__)

    logger.info(
        "app.starting",
        extra={
            "environment": settings.environment,
            "app_name": settings.app_name,
            "version": getattr(settings, "version", "unknown"),
        },
    )

    app = FastAPI(title=settings.app_name)
    app.add_middleware(RequestIDMiddleware)

    # Routers
    app.include_router(health_router)
    app.include_router(dev_ingest_router, prefix="/api")
    app.include_router(dev_runner_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(provider_requests_router, prefix="/api")
    app.include_router(watch_rules_router, prefix="/api")

    logger.info("app.started", extra={"environment": settings.environment, "app_name": settings.app_name})
    return app


app = create_app()