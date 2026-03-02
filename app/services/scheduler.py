from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import record_scheduler_lag, record_scheduler_rule_outcome, record_scheduler_run
from app.db import models
from app.services.rule_runner import run_rule_once

logger = logging.getLogger(__name__)
FAILURE_RETRY_DELAY_SECONDS = 30


@dataclass
class SchedulerRunResult:
    processed_rules: int
    failed_rules: int


def _supports_skip_locked(dialect: object) -> bool:
    supports_skip_locked = getattr(dialect, "supports_for_update_skip_locked", None)
    if supports_skip_locked is not None:
        return bool(supports_skip_locked)

    # SQLAlchemy's Postgres dialect may not expose
    # `supports_for_update_skip_locked`; prefer backend-name detection.
    return getattr(dialect, "name", None) == "postgresql"


def run_due_rules_once(db: Session, *, batch_size: int = 100, rule_limit: int = 20) -> SchedulerRunResult:
    now = datetime.now(timezone.utc)
    due_query = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.is_active.is_(True))
        .filter(
            or_(
                models.WatchSearchRule.next_run_at.is_(None),
                models.WatchSearchRule.next_run_at <= now,
            )
        )
        .order_by(
            models.WatchSearchRule.next_run_at.asc().nullsfirst(), models.WatchSearchRule.created_at.asc()
        )
        .limit(batch_size)
    )

    dialect = db.get_bind().dialect
    if _supports_skip_locked(dialect):
        due_query = due_query.with_for_update(skip_locked=True)
    else:
        # Fallback for engines without SKIP LOCKED support; this keeps row locking
        # semantics but can block under concurrent schedulers.
        due_query = due_query.with_for_update()

    due_rules = due_query.all()

    processed = 0
    failed = 0

    for rule in due_rules:
        processed += 1
        current = datetime.now(timezone.utc)
        if rule.next_run_at is not None:
            lag_seconds = (current - rule.next_run_at).total_seconds()
            record_scheduler_lag(lag_seconds=lag_seconds)
        try:
            run_rule_once(db, user_id=rule.user_id, rule_id=rule.id, limit=rule_limit)
            rule.last_run_at = current
            record_scheduler_rule_outcome(success=True)
            jitter = random.randint(0, max(settings.scheduler_next_run_jitter_seconds, 0))
            rule.next_run_at = current + timedelta(seconds=rule.poll_interval_seconds + jitter)
        except Exception:
            failed += 1
            record_scheduler_rule_outcome(success=False)
            retry_jitter = random.randint(0, max(settings.scheduler_failure_retry_jitter_seconds, 0))
            rule.next_run_at = current + timedelta(seconds=FAILURE_RETRY_DELAY_SECONDS + retry_jitter)
            logger.exception(
                "Scheduler rule execution failed",
                extra={
                    "rule_id": str(rule.id),
                    "user_id": str(rule.user_id),
                    "retry_delay_seconds": FAILURE_RETRY_DELAY_SECONDS,
                },
            )

        db.add(rule)
        db.flush()

    record_scheduler_run(failed_rules=failed)
    return SchedulerRunResult(processed_rules=processed, failed_rules=failed)
