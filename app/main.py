from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings
from app.api.routers.health import router as health_router
from app.api.routers.watch_rules import router as watch_rules_router
from app.api.routers.events import router as events_router
from app.api.routers.dev_ingest import router as dev_ingest_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.include_router(health_router)
    app.include_router(watch_rules_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(dev_ingest_router, prefix="/api")
    return app


app = create_app()
