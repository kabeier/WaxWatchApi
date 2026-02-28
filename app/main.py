# app/main.py
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware import GlobalRateLimitMiddleware, RequestIDMiddleware
from app.api.routers.dev_ingest import router as dev_ingest_router
from app.api.routers.dev_runner import router as dev_runner_router

# dev routers
from app.api.routers.discogs import router as discogs_router
from app.api.routers.events import router as events_router
from app.api.routers.health import router as health_router
from app.api.routers.notifications import router as notifications_router
from app.api.routers.outbound import router as outbound_router
from app.api.routers.profile import router as profile_router
from app.api.routers.provider_requests import router as provider_requests_router
from app.api.routers.search import router as search_router
from app.api.routers.watch_releases import router as watch_releases_router
from app.api.routers.watch_rules import router as watch_rules_router
from app.core.config import settings
from app.core.error_reporting import configure_error_reporting
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimitExceededError

logger = get_logger(__name__)

DEV_ROUTE_ENV_ALLOWLIST = {"dev", "test", "local"}


def _error_response_payload(
    *,
    message: str,
    code: str,
    status: int,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "message": message,
            "code": code,
            "status": status,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def create_app(*, logging_replace_handlers: bool | None = None) -> FastAPI:
    if logging_replace_handlers is None:
        logging_replace_handlers = settings.environment.lower() != "test"

    configure_logging(
        level=settings.log_level,
        json_logs=settings.json_logs,
        replace_handlers=logging_replace_handlers,
    )
    configure_error_reporting()

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=settings.cors_allowed_methods,
        allow_headers=settings.cors_allowed_headers,
        allow_credentials=settings.cors_allow_credentials,
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(GlobalRateLimitMiddleware)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", "-")
        detail = exc.detail
        message = detail if isinstance(detail, str) else "request failed"
        details = None if isinstance(detail, str) else jsonable_encoder(detail)
        request_context = {
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "status_code": exc.status_code,
            "internal_error_code": "http_error",
        }

        if exc.status_code >= 500:
            logger.error(
                "http.exception.server", extra={**request_context, "event_name": "http.exception.server"}
            )
        elif exc.status_code in {401, 403}:
            logger.warning(
                "http.exception.auth", extra={**request_context, "event_name": "http.exception.auth"}
            )

        return JSONResponse(
            status_code=exc.status_code,
            content=_error_response_payload(
                message=message,
                code="http_error",
                status=exc.status_code,
                details=details,
            ),
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_exception_handler(request: Request, exc: RateLimitExceededError):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(exc.retry_after_seconds)},
            content=_error_response_payload(
                message="rate limit exceeded",
                code="rate_limited",
                status=429,
                details={"scope": exc.scope, "retry_after_seconds": exc.retry_after_seconds},
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "-")
        logger.info(
            "request.validation_error",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path),
                "status_code": 422,
                "internal_error_code": "validation_error",
                "event_name": "request.validation_error",
            },
        )
        return JSONResponse(
            status_code=422,
            content=_error_response_payload(
                message="validation error",
                code="validation_error",
                status=422,
                details=jsonable_encoder(exc.errors()),
            ),
        )

    app.include_router(health_router)
    app.include_router(events_router, prefix="/api")
    app.include_router(provider_requests_router, prefix="/api")
    app.include_router(profile_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(watch_rules_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(outbound_router, prefix="/api")
    app.include_router(watch_releases_router, prefix="/api")
    app.include_router(discogs_router, prefix="/api")

    if settings.environment.lower() in DEV_ROUTE_ENV_ALLOWLIST:
        logger.info("dev_routes.enabled", extra={"environment": settings.environment})
        app.include_router(dev_ingest_router, prefix="/api")
        app.include_router(dev_runner_router, prefix="/api")
    else:
        logger.info(
            "dev_routes.disabled",
            extra={"environment": settings.environment, "allowlist": sorted(DEV_ROUTE_ENV_ALLOWLIST)},
        )

    return app


app = create_app()
