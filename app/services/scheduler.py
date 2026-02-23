from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import models
from app.services.rule_runner import run_rule_once


@dataclass
class SchedulerRunResult:
    processed_rules: int
    failed_rules: int


def run_due_rules_once(db: Session, *, batch_size: int = 100, rule_limit: int = 20) -> SchedulerRunResult:
    now = datetime.now(UTC)
    due_rules = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.is_active.is_(True))
        .filter(
            or_(
                models.WatchSearchRule.next_run_at.is_(None),
                models.WatchSearchRule.next_run_at <= now,
            )
        )
        .order_by(models.WatchSearchRule.next_run_at.asc().nullsfirst(), models.WatchSearchRule.created_at.asc())
        .limit(batch_size)
        .all()
    )

    processed = 0
    failed = 0

    for rule in due_rules:
        processed += 1
        try:
            run_rule_once(db, user_id=rule.user_id, rule_id=rule.id, limit=rule_limit)
        except Exception:
            failed += 1

        current = datetime.now(UTC)
        rule.last_run_at = current
        rule.next_run_at = current + timedelta(seconds=rule.poll_interval_seconds)
        db.add(rule)
        db.flush()

    return SchedulerRunResult(processed_rules=processed, failed_rules=failed)
