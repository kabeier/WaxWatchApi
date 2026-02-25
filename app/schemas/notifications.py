from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import EventType, NotificationChannel, NotificationStatus

DeliveryFrequency = Literal["instant", "hourly", "daily"]


class NotificationOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "4c8d9157-4a8c-4ea8-9d27-3ad2fc1e8f95",
                "user_id": "8f2a5009-c0a2-4f90-8f1b-c1716c26bf06",
                "event_id": "f2eec3e4-1f39-4a9f-9f39-2359f3983be0",
                "event_type": "watch_match_found",
                "channel": "realtime",
                "status": "sent",
                "is_read": False,
                "delivered_at": "2026-01-20T12:00:04+00:00",
                "failed_at": None,
                "read_at": None,
                "created_at": "2026-01-20T12:00:03+00:00",
            }
        },
    )
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


class UnreadCountOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"unread_count": 3}})

    unread_count: int
