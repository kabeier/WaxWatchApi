from __future__ import annotations

from datetime import datetime, timezone

import pytest
from celery.exceptions import Retry
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.tasks import deliver_notification_task


def _bind_task_session_local(db_session, monkeypatch) -> None:
    testing_session_local = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.tasks.SessionLocal", testing_session_local)


def test_deliver_notification_task_is_idempotent(db_session, user, monkeypatch):
    _bind_task_session_local(db_session, monkeypatch)

    event = models.Event(
        user_id=user.id,
        type=models.EventType.RULE_CREATED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    notification = models.Notification(
        user_id=user.id,
        event_id=event.id,
        event_type=event.type,
        channel=models.NotificationChannel.email,
        status=models.NotificationStatus.pending,
    )
    db_session.add(notification)
    db_session.flush()

    deliver_notification_task.run(str(notification.id))
    db_session.refresh(notification)
    first_delivered_at = notification.delivered_at
    assert notification.status == models.NotificationStatus.sent
    assert first_delivered_at is not None

    deliver_notification_task.run(str(notification.id))
    db_session.refresh(notification)
    assert notification.status == models.NotificationStatus.sent
    assert notification.delivered_at == first_delivered_at


def test_deliver_notification_task_retries_runtime_errors(db_session, user, monkeypatch):
    _bind_task_session_local(db_session, monkeypatch)

    event = models.Event(
        user_id=user.id,
        type=models.EventType.RULE_CREATED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    notification = models.Notification(
        user_id=user.id,
        event_id=event.id,
        event_type=event.type,
        channel=models.NotificationChannel.email,
        status=models.NotificationStatus.pending,
    )
    db_session.add(notification)
    db_session.flush()

    calls = {"count": 0}

    def _flaky_send_email(_db, *, notification):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary provider failure")
        notification.status = models.NotificationStatus.sent
        notification.delivered_at = datetime.now(timezone.utc)
        notification.updated_at = datetime.now(timezone.utc)
        return notification

    monkeypatch.setattr("app.tasks.send_email", _flaky_send_email)

    with pytest.raises(Retry):
        deliver_notification_task.apply(args=[str(notification.id)])

    result = deliver_notification_task.apply(args=[str(notification.id)])
    assert result.successful()
    assert calls["count"] == 2
    db_session.refresh(notification)
    assert notification.status == models.NotificationStatus.sent


def test_deliver_notification_task_records_retryable_failures_before_retry(db_session, user, monkeypatch):
    _bind_task_session_local(db_session, monkeypatch)

    event = models.Event(
        user_id=user.id,
        type=models.EventType.RULE_CREATED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    notification = models.Notification(
        user_id=user.id,
        event_id=event.id,
        event_type=event.type,
        channel=models.NotificationChannel.email,
        status=models.NotificationStatus.pending,
    )
    db_session.add(notification)
    db_session.flush()

    def _retryable_failure_send_email(_db, *, notification):
        notification.status = models.NotificationStatus.failed
        notification.failed_at = datetime.now(timezone.utc)
        notification.updated_at = datetime.now(timezone.utc)
        raise RuntimeError("transient provider issue")

    monkeypatch.setattr("app.tasks.send_email", _retryable_failure_send_email)

    with pytest.raises(Retry):
        deliver_notification_task.apply(args=[str(notification.id)])

    db_session.refresh(notification)
    assert notification.status == models.NotificationStatus.failed
    assert notification.failed_at is not None
