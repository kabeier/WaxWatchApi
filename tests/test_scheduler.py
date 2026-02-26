from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prometheus_client import generate_latest

from app.db import models
from app.services import scheduler
from app.services.scheduler import FAILURE_RETRY_DELAY_SECONDS, run_due_rules_once


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
