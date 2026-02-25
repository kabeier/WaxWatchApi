from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from celery.exceptions import Retry
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import models
from app.tasks import deliver_notification_task, sync_discogs_lists_task


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


def test_sync_discogs_lists_task_enqueues_once_per_user_under_cooldown(db_session, user, monkeypatch):
    _bind_task_session_local(db_session, monkeypatch)

    now = datetime.now(timezone.utc)
    link = models.ExternalAccountLink(
        user_id=user.id,
        provider=models.Provider.discogs,
        external_user_id="discogs-user",
        access_token="token",
        token_metadata={"oauth_connected": True},
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(link)
    db_session.flush()

    monkeypatch.setattr(settings, "discogs_sync_enabled", True)
    monkeypatch.setattr(settings, "discogs_sync_interval_seconds", 3600)
    monkeypatch.setattr(settings, "discogs_sync_user_batch_size", 10)
    monkeypatch.setattr(settings, "discogs_sync_jitter_seconds", 0)
    monkeypatch.setattr(settings, "discogs_sync_spread_seconds", 0)
    monkeypatch.setattr("app.tasks.random.randint", lambda *_args, **_kwargs: 0)

    queued: list[str] = []

    def _queue_job(*, args, countdown):
        queued.append(args[0])

    monkeypatch.setattr("app.tasks.run_discogs_import_task.apply_async", _queue_job)

    first = sync_discogs_lists_task.run()
    second = sync_discogs_lists_task.run()

    assert first["discovered_users"] == 1
    assert first["enqueued_jobs"] == 1
    assert first["reused_jobs"] == 0

    assert second["discovered_users"] == 1
    assert second["enqueued_jobs"] == 0
    assert second["reused_jobs"] == 1

    jobs = db_session.query(models.ImportJob).filter(models.ImportJob.user_id == user.id).all()
    assert len(jobs) == 1
    assert len(queued) == 1


def test_sync_discogs_lists_task_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "discogs_sync_enabled", False)

    result = sync_discogs_lists_task.run()

    assert result == {"discovered_users": 0, "enqueued_jobs": 0, "reused_jobs": 0, "disabled": 1}


def test_sync_discogs_lists_task_respects_batch_size(db_session, user, user2, monkeypatch):
    _bind_task_session_local(db_session, monkeypatch)

    now = datetime.now(timezone.utc)
    for account_user in (user, user2):
        db_session.add(
            models.ExternalAccountLink(
                user_id=account_user.id,
                provider=models.Provider.discogs,
                external_user_id=f"discogs-{account_user.id}",
                access_token="token",
                token_metadata={"oauth_connected": True},
                connected_at=now,
                created_at=now,
                updated_at=now - timedelta(minutes=5),
            )
        )
    db_session.flush()

    monkeypatch.setattr(settings, "discogs_sync_enabled", True)
    monkeypatch.setattr(settings, "discogs_sync_interval_seconds", 3600)
    monkeypatch.setattr(settings, "discogs_sync_user_batch_size", 1)
    monkeypatch.setattr(settings, "discogs_sync_jitter_seconds", 0)
    monkeypatch.setattr(settings, "discogs_sync_spread_seconds", 0)
    monkeypatch.setattr("app.tasks.random.randint", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr("app.tasks.run_discogs_import_task.apply_async", lambda **_kwargs: None)

    result = sync_discogs_lists_task.run()

    assert result["discovered_users"] == 1
    assert result["enqueued_jobs"] == 1


def test_deliver_notification_task_defers_during_quiet_hours(db_session, user, monkeypatch):
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
    db_session.add(
        models.UserNotificationPreference(
            user_id=user.id,
            email_enabled=True,
            realtime_enabled=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
            timezone_override="UTC",
            delivery_frequency="instant",
            event_toggles={models.EventType.RULE_CREATED.value: True},
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        "app.services.notifications.datetime",
        type(
            "_FixedDatetime",
            (),
            {"now": staticmethod(lambda _tz=None: datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc))},
        ),
    )

    queued: list[int] = []

    def _capture_apply_async(*, args, countdown):
        _ = args
        queued.append(countdown)

    monkeypatch.setattr("app.tasks.deliver_notification_task.apply_async", _capture_apply_async)
    monkeypatch.setattr(
        "app.tasks.send_email", lambda *_args, **_kwargs: pytest.fail("send_email should not run")
    )

    deliver_notification_task.run(str(notification.id))

    db_session.refresh(notification)
    assert notification.status == models.NotificationStatus.pending
    assert queued and queued[0] > 0
