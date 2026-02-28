from __future__ import annotations

import uuid

import pytest

from app.core.celery_app import celery_app
from app.db import models
from app.tasks import (
    deliver_notification_task,
    poll_due_rules_task,
    run_discogs_import_task,
)


class _FakeDB:
    def __init__(self, notification=None):
        self._notification = notification
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def query(self, _model):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self._notification

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


class _FakeNotification:
    def __init__(self, *, channel, status=models.NotificationStatus.pending):
        self.id = uuid.uuid4()
        self.channel = channel
        self.status = status


def test_poll_due_rules_task_rolls_back_and_closes_session(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("scheduler crashed")

    monkeypatch.setattr("app.tasks.run_due_rules_once", _raise)

    with pytest.raises(RuntimeError, match="scheduler crashed"):
        poll_due_rules_task.run()

    assert db.commits == 0
    assert db.rollbacks == 1
    assert db.closed == 1


def test_run_discogs_import_task_rolls_back_on_error(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("discogs import failed")

    monkeypatch.setattr("app.tasks.discogs_import_service.execute_import_job", _raise)

    with pytest.raises(RuntimeError, match="discogs import failed"):
        run_discogs_import_task.run(str(uuid.uuid4()))

    assert db.rollbacks == 1
    assert db.closed == 1


def test_deliver_notification_task_realtime_channel_uses_async_publish(monkeypatch):
    notification = _FakeNotification(channel=models.NotificationChannel.realtime)
    db = _FakeDB(notification=notification)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    called = {"publish": 0}

    async def _publish(_db, *, notification):
        called["publish"] += 1
        notification.status = models.NotificationStatus.sent

    monkeypatch.setattr("app.tasks.publish_realtime", _publish)
    monkeypatch.setattr("app.tasks.defer_delivery_seconds", lambda *_args, **_kwargs: None)

    deliver_notification_task.run(str(notification.id))

    assert called["publish"] == 1
    assert db.commits == 1
    assert db.rollbacks == 0
    assert db.closed == 1


def test_deliver_notification_task_raises_for_unsupported_channel(monkeypatch):
    notification = _FakeNotification(channel="sms")
    db = _FakeDB(notification=notification)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    monkeypatch.setattr("app.tasks.defer_delivery_seconds", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="unsupported notification channel"):
        deliver_notification_task.run(str(notification.id))

    assert db.commits == 1
    assert db.rollbacks == 0
    assert db.closed == 1


def test_deliver_notification_task_logs_missing_notification_context(monkeypatch):
    db = _FakeDB(notification=None)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    warned: dict[str, object] = {}

    def _capture_warning(message, *, extra):
        warned["message"] = message
        warned["extra"] = extra

    monkeypatch.setattr("app.tasks.logger.warning", _capture_warning)

    notification_id = str(uuid.uuid4())
    deliver_notification_task.run(notification_id)

    assert warned == {
        "message": "notifications.delivery.notification_not_found",
        "extra": {"notification_id": notification_id, "likely_race": True},
    }
    assert db.commits == 0
    assert db.rollbacks == 0
    assert db.closed == 1


def test_poll_due_rules_task_logs_structured_event_on_failure(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("scheduler crashed")

    captured: dict[str, object] = {}

    def _capture_exception(message, *, extra):
        captured["message"] = message
        captured["extra"] = extra

    monkeypatch.setattr("app.tasks.run_due_rules_once", _raise)
    monkeypatch.setattr("app.tasks.logger.exception", _capture_exception)

    with pytest.raises(RuntimeError, match="scheduler crashed"):
        poll_due_rules_task.run()

    assert captured["message"] == "tasks.poll_due_rules.failed"
    assert captured["extra"]["task_name"] == "poll_due_rules_task"


def test_run_discogs_import_task_logs_structured_event_on_failure(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("discogs import failed")

    captured: dict[str, object] = {}

    def _capture_exception(message, *, extra):
        captured["message"] = message
        captured["extra"] = extra

    monkeypatch.setattr("app.tasks.discogs_import_service.execute_import_job", _raise)
    monkeypatch.setattr("app.tasks.logger.exception", _capture_exception)

    job_id = str(uuid.uuid4())
    with pytest.raises(RuntimeError, match="discogs import failed"):
        run_discogs_import_task.run(job_id)

    assert captured == {
        "message": "tasks.run_discogs_import.failed",
        "extra": {"task_name": "run_discogs_import_task", "job_id": job_id},
    }


def test_celery_beat_schedule_includes_discogs_sync_task():
    schedule = celery_app.conf.beat_schedule

    assert "sync-discogs-lists" in schedule
    assert schedule["sync-discogs-lists"]["task"] == "app.tasks.sync_discogs_lists"
    assert schedule["sync-discogs-lists"]["schedule"] >= 60
