from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.api.pagination import encode_created_id_cursor
from app.db import models
from app.services.notifications import enqueue_from_event, publish_realtime, send_email, stream_broker


def _create_event(db_session, user_id: uuid.UUID) -> models.Event:
    event = models.Event(
        user_id=user_id,
        type=models.EventType.NEW_MATCH,
        payload={"title": "Test Match"},
        created_at=datetime.now(timezone.utc),
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


def test_notifications_pagination_offset_cursor_and_empty_page(client, db_session, user, headers):
    shared_ts = datetime.now(timezone.utc)
    event = models.Event(user_id=user.id, type=models.EventType.NEW_MATCH, payload=None, created_at=shared_ts)
    db_session.add(event)
    db_session.flush()

    notification_a = models.Notification(
        user_id=user.id,
        event_id=event.id,
        event_type=models.EventType.NEW_MATCH,
        channel=models.NotificationChannel.email,
        status=models.NotificationStatus.pending,
        created_at=shared_ts,
        updated_at=shared_ts,
    )
    notification_b = models.Notification(
        user_id=user.id,
        event_id=event.id,
        event_type=models.EventType.NEW_MATCH,
        channel=models.NotificationChannel.realtime,
        status=models.NotificationStatus.pending,
        created_at=shared_ts,
        updated_at=shared_ts,
    )
    db_session.add_all([notification_a, notification_b])
    db_session.flush()

    ordered = sorted([notification_a, notification_b], key=lambda n: n.id, reverse=True)
    cursor = encode_created_id_cursor(created_at=ordered[0].created_at, row_id=ordered[0].id)
    auth_headers = headers(user.id)

    offset_resp = client.get("/api/notifications?limit=1&offset=1", headers=auth_headers)
    assert offset_resp.status_code == 200
    assert offset_resp.json()[0]["id"] == str(ordered[1].id)

    cursor_resp = client.get(f"/api/notifications?limit=2&cursor={cursor}", headers=auth_headers)
    assert cursor_resp.status_code == 200
    assert [r["id"] for r in cursor_resp.json()] == [str(ordered[1].id)]

    empty_resp = client.get("/api/notifications?limit=2&offset=99", headers=auth_headers)
    assert empty_resp.status_code == 200
    assert empty_resp.json() == []


def test_notification_preferences_disable_delivery_channels(db_session, user):
    db_session.add(
        models.UserNotificationPreference(
            user_id=user.id,
            email_enabled=False,
            realtime_enabled=False,
            event_toggles={models.EventType.NEW_MATCH.value: True},
        )
    )
    db_session.flush()

    event = _create_event(db_session, user.id)
    notifications = enqueue_from_event(db_session, event=event)

    assert notifications == []
    assert db_session.query(models.Notification).filter(models.Notification.event_id == event.id).count() == 0


def test_profile_notification_preference_changes_affect_enqueue(client, db_session, user, headers):
    response = client.patch(
        "/api/me",
        headers=headers(user.id),
        json={"preferences": {"notifications_email": True, "notifications_push": False}},
    )
    assert response.status_code == 200

    event = _create_event(db_session, user.id)
    notifications = enqueue_from_event(db_session, event=event)

    assert len(notifications) == 1
    assert notifications[0].channel == models.NotificationChannel.email
