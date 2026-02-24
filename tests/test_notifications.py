from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from app.db import models
from app.services.notifications import enqueue_from_event, publish_realtime, send_email, stream_broker


def _create_event(db_session, user_id: uuid.UUID) -> models.Event:
    event = models.Event(
        user_id=user_id,
        type=models.EventType.NEW_MATCH,
        payload={"title": "Test Match"},
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    db_session.flush()
    return event


def test_enqueue_from_event_is_idempotent(db_session, user):
    event = _create_event(db_session, user.id)

    first = enqueue_from_event(db_session, event=event)
    second = enqueue_from_event(db_session, event=event)

    assert len(first) == 2
    assert len(second) == 2

    notifications = (
        db_session.query(models.Notification).filter(models.Notification.event_id == event.id).all()
    )
    assert len(notifications) == 2


def test_notifications_endpoints(client, db_session, user, headers):
    event = _create_event(db_session, user.id)
    enqueue_from_event(db_session, event=event)
    db_session.flush()

    auth_headers = headers(user.id)

    list_response = client.get("/api/notifications", headers=auth_headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 2

    unread_response = client.get("/api/notifications/unread-count", headers=auth_headers)
    assert unread_response.status_code == 200
    assert unread_response.json()["unread_count"] == 2

    notification_id = payload[0]["id"]
    mark_response = client.post(f"/api/notifications/{notification_id}/read", headers=auth_headers)
    assert mark_response.status_code == 200
    assert mark_response.json()["is_read"] is True

    unread_response_after = client.get("/api/notifications/unread-count", headers=auth_headers)
    assert unread_response_after.status_code == 200
    assert unread_response_after.json()["unread_count"] == 1


def test_send_and_publish_are_idempotent(db_session, user):
    event = _create_event(db_session, user.id)
    notifications = enqueue_from_event(db_session, event=event)

    email_notification = next(n for n in notifications if n.channel == models.NotificationChannel.email)
    realtime_notification = next(n for n in notifications if n.channel == models.NotificationChannel.realtime)

    send_email(db_session, notification=email_notification)
    sent_at = email_notification.delivered_at
    send_email(db_session, notification=email_notification)
    assert email_notification.delivered_at == sent_at

    async def _run_realtime():
        queue = await stream_broker.subscribe(user.id)
        await publish_realtime(db_session, notification=realtime_notification)
        first_payload = await asyncio.wait_for(queue.get(), timeout=1)
        delivered_at = realtime_notification.delivered_at
        await publish_realtime(db_session, notification=realtime_notification)
        await stream_broker.unsubscribe(user.id, queue)
        return first_payload, delivered_at

    first_payload, delivered_at = asyncio.run(_run_realtime())
    assert first_payload["event_id"] == str(event.id)
    assert realtime_notification.delivered_at == delivered_at
