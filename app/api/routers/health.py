from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.core.metrics import metrics_payload

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request, db: Session = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "-")

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("health.ready.db_error", extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail="db not ready") from None

    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)
