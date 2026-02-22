from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.db import models
from app.schemas.events import EventOut

logger = get_logger(__name__)
router = APIRouter(prefix="/events", tags=["events"])


def get_current_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


@router.get("", response_model=list[EventOut])
def list_events(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=200),
):
    request_id = getattr(request.state, "request_id", "-")

    try:
        events = (
            db.query(models.Event)
            .filter(models.Event.user_id == user_id)
            .order_by(models.Event.created_at.desc())
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        logger.exception(
            "events.list.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "limit": limit},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.debug(
        "events.list.success",
        extra={"request_id": request_id, "user_id": str(user_id), "limit": limit, "count": len(events)},
    )
    return events
