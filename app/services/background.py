from __future__ import annotations

from uuid import UUID

from app.tasks import backfill_rule_matches_task as celery_backfill_rule_matches_task


def enqueue_backfill_rule_matches_task(user_id: UUID, rule_id: UUID) -> None:
    celery_backfill_rule_matches_task.delay(str(user_id), str(rule_id))


def backfill_rule_matches_task(user_id: UUID, rule_id: UUID) -> None:
    celery_backfill_rule_matches_task.run(str(user_id), str(rule_id))
