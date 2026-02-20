from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.events import EventOut

router = APIRouter(prefix="/events", tags=["events"])


def get_current_user_id(x_user_id: UUID = Header(..., alias="X-User-Id")) -> UUID:
    return x_user_id


@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=200),
):
    q = (
        db.query(models.Event)
        .filter(models.Event.user_id == user_id)
        .order_by(models.Event.created_at.desc())
        .limit(limit)
    )
    return list(q.all())