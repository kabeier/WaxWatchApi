from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.services.task_dispatcher import enqueue_notification_delivery

logger = get_logger(__name__)


def _default_event_toggles() -> dict[str, bool]:
    return {event_type.value: True for event_type in models.EventType}


def _preference_allows_event(
    preference: models.UserNotificationPreference | None, event_type: models.EventType
) -> bool:
    if preference is None:
        return True

    toggles = preference.event_toggles or {}
    return bool(toggles.get(event_type.value, True))


class NotificationStreamBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = defaultdict(set)
        self._lock = Lock()

    async def subscribe(self, user_id: UUID) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        with self._lock:
            self._subscribers[str(user_id)].add(queue)
        return queue

    async def unsubscribe(self, user_id: UUID, queue: asyncio.Queue[dict]) -> None:
        with self._lock:
            user_queues = self._subscribers.get(str(user_id), set())
            user_queues.discard(queue)
            if not user_queues:
                self._subscribers.pop(str(user_id), None)

    async def publish(self, user_id: UUID, payload: dict) -> None:
        with self._lock:
            user_queues = list(self._subscribers.get(str(user_id), set()))
        for queue in user_queues:
            await queue.put(payload)


stream_broker = NotificationStreamBroker()


def get_or_create_preferences(db: Session, *, user_id: UUID) -> models.UserNotificationPreference:
    preference = (
        db.query(models.UserNotificationPreference)
        .filter(models.UserNotificationPreference.user_id == user_id)
        .one_or_none()
    )
    if preference:
        return preference

    preference = models.UserNotificationPreference(
        user_id=user_id,
        email_enabled=True,
        event_toggles=_default_event_toggles(),
    )
    db.add(preference)
    db.flush()
    return preference


def enqueue_from_event(
    db: Session,
    *,
    event: models.Event,
    channels: tuple[models.NotificationChannel, ...] = (
        models.NotificationChannel.email,
        models.NotificationChannel.realtime,
    ),
) -> list[models.Notification]:
    preference = get_or_create_preferences(db, user_id=event.user_id)
    if not _preference_allows_event(preference, event.type):
        return []

    notifications: list[models.Notification] = []
    for channel in channels:
        notification = (
            db.query(models.Notification)
            .filter(models.Notification.event_id == event.id, models.Notification.channel == channel)
            .one_or_none()
        )
        if notification is None:
            notification = models.Notification(
                user_id=event.user_id,
                event_id=event.id,
                event_type=event.type,
                channel=channel,
                status=models.NotificationStatus.pending,
            )
            db.add(notification)
            db.flush()
        notifications.append(notification)
        if notification.status == models.NotificationStatus.pending:
            enqueue_notification_delivery(str(notification.id))

    return notifications


def send_email(db: Session, *, notification: models.Notification) -> models.Notification:
    if notification.channel != models.NotificationChannel.email:
        raise ValueError("notification channel must be email")

    if notification.status == models.NotificationStatus.sent:
        return notification

    preference = get_or_create_preferences(db, user_id=notification.user_id)
    if not preference.email_enabled:
        return notification

    now = datetime.now(timezone.utc)
    notification.status = models.NotificationStatus.sent
    notification.delivered_at = now
    notification.failed_at = None
    notification.updated_at = now

    logger.info(
        "notifications.email.sent",
        extra={"notification_id": str(notification.id), "event_id": str(notification.event_id)},
    )
    db.flush()
    return notification


async def publish_realtime(db: Session, *, notification: models.Notification) -> models.Notification:
    if notification.channel != models.NotificationChannel.realtime:
        raise ValueError("notification channel must be realtime")

    if notification.status == models.NotificationStatus.sent:
        return notification

    payload = {
        "notification_id": str(notification.id),
        "event_id": str(notification.event_id),
        "event_type": notification.event_type.value,
        "created_at": notification.created_at.isoformat(),
    }
    await stream_broker.publish(notification.user_id, payload)

    now = datetime.now(timezone.utc)
    notification.status = models.NotificationStatus.sent
    notification.delivered_at = now
    notification.failed_at = None
    notification.updated_at = now
    db.flush()
    return notification
