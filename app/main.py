from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings
from app.api.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.include_router(health_router)

    return app


app = create_app()
