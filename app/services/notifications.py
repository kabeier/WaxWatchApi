from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.services.email_provider import EmailDeliveryRequest, get_email_provider
from app.services.task_dispatcher import enqueue_notification_delivery

logger = get_logger(__name__)

DELIVERY_FREQUENCY_SECONDS = {
    "instant": 0,
    "hourly": 60 * 60,
    "daily": 60 * 60 * 24,
}


def _default_event_toggles() -> dict[str, bool]:
    return {event_type.value: True for event_type in models.EventType}


def _preference_allows_event(
    preference: models.UserNotificationPreference | None, event_type: models.EventType
) -> bool:
    if preference is None:
        return True

    toggles = preference.event_toggles or {}
    return bool(toggles.get(event_type.value, True))


def _resolve_timezone(preference: models.UserNotificationPreference, user_timezone: str | None) -> ZoneInfo:
    candidate = preference.timezone_override or user_timezone or "UTC"
    try:
        return ZoneInfo(candidate)
    except Exception:
        logger.warning("notifications.preferences.invalid_timezone", extra={"timezone": candidate})
        return ZoneInfo("UTC")


def _is_within_quiet_hours(hour: int, quiet_start: int | None, quiet_end: int | None) -> bool:
    if quiet_start is None or quiet_end is None:
        return False
    if quiet_start == quiet_end:
        return True
    if quiet_start < quiet_end:
        return quiet_start <= hour < quiet_end
    return hour >= quiet_start or hour < quiet_end


def _next_quiet_window_end(
    now_utc: datetime,
    *,
    timezone_info: ZoneInfo,
    quiet_start: int | None,
    quiet_end: int | None,
) -> datetime | None:
    if quiet_start is None or quiet_end is None:
        return None

    local_now = now_utc.astimezone(timezone_info)
    if not _is_within_quiet_hours(local_now.hour, quiet_start, quiet_end):
        return None

    if quiet_start < quiet_end:
        end_local = local_now.replace(hour=quiet_end, minute=0, second=0, microsecond=0)
        if end_local <= local_now:
            end_local = end_local + timedelta(days=1)
    else:
        end_local = local_now.replace(hour=quiet_end, minute=0, second=0, microsecond=0)
        if local_now.hour >= quiet_start:
            end_local = end_local + timedelta(days=1)

    return end_local.astimezone(timezone.utc)


def _frequency_defer_until(
    db: Session, *, notification: models.Notification, frequency: str
) -> datetime | None:
    interval_seconds = DELIVERY_FREQUENCY_SECONDS.get(frequency, 0)
    if interval_seconds <= 0:
        return None

    last_delivered_at = (
        db.query(func.max(models.Notification.delivered_at))
        .filter(models.Notification.user_id == notification.user_id)
        .filter(models.Notification.channel == notification.channel)
        .filter(models.Notification.status == models.NotificationStatus.sent)
        .scalar()
    )
    if last_delivered_at is None:
        return None

    return last_delivered_at + timedelta(seconds=interval_seconds)


def next_delivery_time(
    db: Session,
    *,
    notification: models.Notification,
    now_utc: datetime | None = None,
) -> datetime | None:
    now = now_utc or datetime.now(timezone.utc)
    preference = get_or_create_preferences(db, user_id=notification.user_id)

    candidate = now
    timezone_info = _resolve_timezone(preference, notification.user.timezone)

    quiet_until = _next_quiet_window_end(
        candidate,
        timezone_info=timezone_info,
        quiet_start=preference.quiet_hours_start,
        quiet_end=preference.quiet_hours_end,
    )
    if quiet_until is not None and quiet_until > candidate:
        candidate = quiet_until

    frequency_until = _frequency_defer_until(
        db,
        notification=notification,
        frequency=preference.delivery_frequency,
    )
    if frequency_until is not None and frequency_until > candidate:
        candidate = frequency_until

    quiet_after_frequency = _next_quiet_window_end(
        candidate,
        timezone_info=timezone_info,
        quiet_start=preference.quiet_hours_start,
        quiet_end=preference.quiet_hours_end,
    )
    if quiet_after_frequency is not None and quiet_after_frequency > candidate:
        candidate = quiet_after_frequency

    if candidate <= now:
        return None
    return candidate


def defer_delivery_seconds(
    db: Session,
    *,
    notification: models.Notification,
    now_utc: datetime | None = None,
) -> int | None:
    next_at = next_delivery_time(db, notification=notification, now_utc=now_utc)
    if next_at is None:
        return None

    now = now_utc or datetime.now(timezone.utc)
    delta = int((next_at - now).total_seconds())
    return max(delta, 1)


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
        realtime_enabled=True,
        delivery_frequency="instant",
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
    enabled_channels = {models.NotificationChannel.realtime, models.NotificationChannel.email}
    if not preference.email_enabled:
        enabled_channels.discard(models.NotificationChannel.email)
    if not preference.realtime_enabled:
        enabled_channels.discard(models.NotificationChannel.realtime)

    for channel in channels:
        if channel not in enabled_channels:
            continue
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
            countdown = defer_delivery_seconds(db, notification=notification)
            enqueue_notification_delivery(str(notification.id), countdown=countdown)

    return notifications


def send_email(db: Session, *, notification: models.Notification) -> models.Notification:
    if notification.channel != models.NotificationChannel.email:
        raise ValueError("notification channel must be email")

    if notification.status == models.NotificationStatus.sent:
        return notification

    preference = get_or_create_preferences(db, user_id=notification.user_id)
    if not preference.email_enabled:
        return notification

    provider = get_email_provider()
    request = EmailDeliveryRequest(
        to_address=notification.user.email,
        subject=f"WaxWatch notification: {notification.event_type.value}",
        text_body=(
            f"You have a new {notification.event_type.value} notification. "
            f"Notification id: {notification.id}."
        ),
    )
    delivery_result = provider.send_email(request)

    now = datetime.now(timezone.utc)
    if delivery_result.success:
        notification.status = models.NotificationStatus.sent
        notification.delivered_at = now
        notification.failed_at = None
        notification.updated_at = now

        logger.info(
            "notifications.email.sent",
            extra={
                "notification_id": str(notification.id),
                "event_id": str(notification.event_id),
                "provider_message_id": delivery_result.provider_message_id,
            },
        )
    else:
        notification.status = models.NotificationStatus.failed
        notification.failed_at = now
        notification.updated_at = now

        logger.warning(
            "notifications.email.failed",
            extra={
                "notification_id": str(notification.id),
                "event_id": str(notification.event_id),
                "retryable": delivery_result.retryable,
                "error_code": delivery_result.error_code,
                "error_message": delivery_result.error_message,
            },
        )
        if delivery_result.retryable:
            db.flush()
            raise RuntimeError(delivery_result.error_message or "email provider temporary failure")

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
