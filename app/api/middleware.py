from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.core.metrics import record_request_latency
from app.core.request_context import reset_request_id, set_request_id

logger = get_logger("app.request")

try:
    import sentry_sdk
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request_id_token = set_request_id(request_id)

        start = time.perf_counter()

        logger.info(
            "request.start",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "user_id": getattr(request.state, "user_id", None),
            },
        )

        if sentry_sdk is not None:
            sentry_sdk.set_tag("request_id", request_id)
            sentry_sdk.set_context(
                "request", {"id": request_id, "path": request.url.path, "method": request.method}
            )

        try:
            response = await call_next(request)
        except Exception:
            duration_seconds = time.perf_counter() - start
            duration_ms = int(duration_seconds * 1000)
            logger.exception(
                "request.unhandled_exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "user_id": getattr(request.state, "user_id", None),
                    "duration_ms": duration_ms,
                },
            )
            record_request_latency(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_seconds=duration_seconds,
            )
            reset_request_id(request_id_token)
            raise

        duration_seconds = time.perf_counter() - start
        duration_ms = int(duration_seconds * 1000)

        logger.info(
            "request.end",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "user_id": getattr(request.state, "user_id", None),
                "duration_ms": duration_ms,
            },
        )

        record_request_latency(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )

        response.headers["x-request-id"] = request_id
        reset_request_id(request_id_token)
        return response
