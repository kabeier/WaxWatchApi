from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.db.models import EventType, NotificationChannel, NotificationStatus


class NotificationOut(BaseModel):
    id: UUID
    user_id: UUID
    event_id: UUID
    event_type: EventType
    channel: NotificationChannel
    status: NotificationStatus
    is_read: bool
    delivered_at: datetime | None
    failed_at: datetime | None
    read_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class UnreadCountOut(BaseModel):
    unread_count: int
