from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import models
from app.services.scheduler import run_due_rules_once


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
