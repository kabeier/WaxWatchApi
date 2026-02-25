from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import metrics_payload

logger = get_logger(__name__)
router = APIRouter(tags=["health"])
READINESS_PROBE_TIMEOUT_SECONDS = 1.0


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request, db: Session = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "-")
    checks: dict[str, dict[str, str]] = {}

    db_ok, db_reason = _probe_db(db, timeout_seconds=READINESS_PROBE_TIMEOUT_SECONDS)
    checks["db"] = _probe_status(db_ok, db_reason)

    redis_required = _redis_required()
    if redis_required:
        redis_ok, redis_reason = _probe_redis(timeout_seconds=READINESS_PROBE_TIMEOUT_SECONDS)
        checks["redis"] = _probe_status(redis_ok, redis_reason)
    else:
        checks["redis"] = {
            "status": "skipped",
            "reason": "redis readiness check skipped because celery tasks are eager in this environment",
        }

    failed_required_checks = {
        name: details
        for name, details in checks.items()
        if details["status"] == "failed" and (name != "redis" or redis_required)
    }
    if failed_required_checks:
        logger.error(
            "health.ready.dependency_failed",
            extra={
                "request_id": request_id,
                "failed_checks": list(failed_required_checks),
                "checks": checks,
            },
        )
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "reason": "required dependency checks failed",
                "checks": checks,
            },
        )

    return {"status": "ready", "checks": checks}


def _probe_status(ok: bool, reason: str | None) -> dict[str, str]:
    if ok:
        return {"status": "ok"}
    return {"status": "failed", "reason": reason or "probe failed"}


def _run_with_timeout(func, timeout_seconds: float):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        return future.result(timeout=timeout_seconds)


def _probe_db(db: Session, *, timeout_seconds: float) -> tuple[bool, str | None]:
    try:
        _run_with_timeout(lambda: db.execute(text("SELECT 1")), timeout_seconds=timeout_seconds)
    except TimeoutError:
        return False, f"db readiness probe timed out after {timeout_seconds:.1f}s"
    except SQLAlchemyError as exc:
        return False, f"db readiness probe failed: {exc.__class__.__name__}"
    return True, None


def _probe_redis(*, timeout_seconds: float) -> tuple[bool, str | None]:
    redis_client = Redis.from_url(
        settings.celery_broker_url,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
    )

    try:
        _run_with_timeout(redis_client.ping, timeout_seconds=timeout_seconds)
    except TimeoutError:
        return False, f"redis readiness probe timed out after {timeout_seconds:.1f}s"
    except RedisError as exc:
        return False, f"redis readiness probe failed: {exc.__class__.__name__}"
    finally:
        redis_client.close()

    return True, None


def _redis_required() -> bool:
    return not settings.celery_task_always_eager


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)
