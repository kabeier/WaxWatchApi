from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.db import models
from app.schemas.notifications import NotificationOut, UnreadCountOut
from app.services.notifications import stream_broker

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=200),
):
    return (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.created_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    notification = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == user_id)
        .one_or_none()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="notification not found")

    if not notification.is_read:
        now = datetime.now(UTC)
        notification.is_read = True
        notification.read_at = now
        notification.updated_at = now
        db.flush()
    return notification


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    unread_count = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id, models.Notification.is_read.is_(False))
        .count()
    )
    return UnreadCountOut(unread_count=unread_count)


@router.get("/stream/events")
async def stream_events(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
):
    queue = await stream_broker.subscribe(user_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                    yield f"event: notification\ndata: {json.dumps(event)}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            await stream_broker.unsubscribe(user_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
