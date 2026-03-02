from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from prometheus_client import generate_latest

from app.db import models
from app.db.base import SessionLocal
from app.services import scheduler
from app.services.scheduler import (
    FAILURE_RETRY_DELAY_SECONDS,
    _supports_skip_locked,
    run_due_rules_once,
)


def test_scheduler_runs_due_rules_and_advances_schedule(db_session, user):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="due rule",
        query={"keywords": ["primus"], "sources": ["discogs"]},
        is_active=True,
        poll_interval_seconds=120,
        next_run_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add(rule)
    db_session.flush()

    result = run_due_rules_once(db_session, batch_size=10, rule_limit=5)

    assert result.processed_rules == 1
    assert result.failed_rules == 0

    db_session.refresh(rule)
    assert rule.last_run_at is not None
    assert rule.next_run_at is not None
    assert rule.next_run_at > rule.last_run_at


def test_scheduler_failure_increments_failed_and_uses_retry_delay(db_session, user, monkeypatch):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="failing rule",
        query={"keywords": ["primus"], "sources": ["discogs"]},
        is_active=True,
        poll_interval_seconds=120,
        last_run_at=None,
        next_run_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add(rule)
    db_session.flush()

    def _raise_once(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "run_rule_once", _raise_once)
    monkeypatch.setattr(scheduler.random, "randint", lambda *_args, **_kwargs: 0)

    result = run_due_rules_once(db_session, batch_size=10, rule_limit=5)

    assert result.processed_rules == 1
    assert result.failed_rules == 1

    db_session.refresh(rule)
    assert rule.last_run_at is None
    assert rule.next_run_at is not None
    retry_delta = rule.next_run_at - datetime.now(timezone.utc)
    assert timedelta(seconds=0) < retry_delta <= timedelta(seconds=FAILURE_RETRY_DELAY_SECONDS + 2)


def test_scheduler_records_metrics(db_session, user):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="due rule metrics",
        query={"keywords": ["primus"], "sources": ["discogs"]},
        is_active=True,
        poll_interval_seconds=120,
        next_run_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add(rule)
    db_session.flush()

    run_due_rules_once(db_session, batch_size=10, rule_limit=5)

    payload = generate_latest().decode("utf-8")
    assert 'waxwatch_scheduler_rule_outcomes_total{outcome="success"}' in payload
    assert 'waxwatch_scheduler_runs_total{outcome="success"}' in payload
    assert "waxwatch_scheduler_lag_seconds" in payload


def test_scheduler_claims_due_rules_once_across_concurrent_sessions(monkeypatch):
    seen_rule_ids: list[uuid.UUID] = []

    def _record_rule_run(_db, *, rule_id: uuid.UUID, **_kwargs):
        seen_rule_ids.append(rule_id)

    monkeypatch.setattr(scheduler, "run_rule_once", _record_rule_run)
    monkeypatch.setattr(scheduler.random, "randint", lambda *_args, **_kwargs: 0)

    seed_session = SessionLocal()
    verify_session = SessionLocal()
    worker_one = SessionLocal()
    worker_two = SessionLocal()

    user_id: uuid.UUID | None = None

    try:
        user = models.User(
            email=f"concurrency-{uuid.uuid4()}@example.com",
            hashed_password="not-a-real-hash",
            display_name="Concurrency User",
            is_active=True,
        )
        seed_session.add(user)
        seed_session.flush()
        user_id = user.id

        due_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        seed_session.add_all(
            [
                models.WatchSearchRule(
                    user_id=user.id,
                    name="concurrency rule 1",
                    query={"keywords": ["primus"], "sources": ["discogs"]},
                    is_active=True,
                    poll_interval_seconds=120,
                    next_run_at=due_at,
                ),
                models.WatchSearchRule(
                    user_id=user.id,
                    name="concurrency rule 2",
                    query={"keywords": ["rush"], "sources": ["discogs"]},
                    is_active=True,
                    poll_interval_seconds=120,
                    next_run_at=due_at,
                ),
            ]
        )
        seed_session.commit()

        result_one = run_due_rules_once(worker_one, batch_size=10, rule_limit=5)
        result_two = run_due_rules_once(worker_two, batch_size=10, rule_limit=5)

        worker_one.commit()
        worker_two.commit()

        assert result_one.processed_rules == 2
        assert result_two.processed_rules == 0
        assert len(seen_rule_ids) == 2
        assert len(set(seen_rule_ids)) == 2

        refreshed_rules = (
            verify_session.query(models.WatchSearchRule)
            .filter(models.WatchSearchRule.user_id == user.id)
            .order_by(models.WatchSearchRule.created_at.asc())
            .all()
        )
        assert len(refreshed_rules) == 2
        assert all(rule.next_run_at is not None for rule in refreshed_rules)
        assert all(rule.last_run_at is not None for rule in refreshed_rules)
    finally:
        worker_two.close()
        worker_one.close()
        verify_session.close()
        seed_session.close()

        if user_id is not None:
            cleanup_session = SessionLocal()
            try:
                cleanup_user = cleanup_session.get(models.User, user_id)
                if cleanup_user is not None:
                    cleanup_session.delete(cleanup_user)
                    cleanup_session.commit()
            finally:
                cleanup_session.close()


def test_supports_skip_locked_uses_backend_name_when_dialect_flag_is_missing():
    assert _supports_skip_locked(SimpleNamespace(name="postgresql")) is True
    assert _supports_skip_locked(SimpleNamespace(name="sqlite")) is False


def test_supports_skip_locked_prefers_explicit_dialect_flag():
    assert (
        _supports_skip_locked(SimpleNamespace(name="postgresql", supports_for_update_skip_locked=False))
        is False
    )
    assert _supports_skip_locked(SimpleNamespace(name="sqlite", supports_for_update_skip_locked=True)) is True
