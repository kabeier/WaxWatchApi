from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.api.pagination import PaginationParams, apply_created_id_pagination, get_pagination_params
from app.core.logging import get_logger
from app.db import models
from app.schemas.events import EventOut

logger = get_logger(__name__)
router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventOut])
def list_events(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    request_id = getattr(request.state, "request_id", "-")

    try:
        events = apply_created_id_pagination(
            db.query(models.Event).filter(models.Event.user_id == user_id),
            models.Event,
            pagination,
        ).all()
    except SQLAlchemyError:
        logger.exception(
            "events.list.db_error",
            extra={
                "request_id": request_id,
                "user_id": str(user_id),
                "limit": pagination.limit,
                "offset": pagination.offset,
                "cursor": pagination.cursor,
            },
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.debug(
        "events.list.success",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "limit": pagination.limit,
            "offset": pagination.offset,
            "cursor": pagination.cursor,
            "count": len(events),
        },
    )
    return events
