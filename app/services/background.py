from __future__ import annotations

from uuid import UUID

from app.db.base import SessionLocal
from app.services.backfill import backfill_matches_for_rule


def backfill_rule_matches_task(user_id: UUID, rule_id: UUID) -> None:
    db = SessionLocal()
    try:
        backfill_matches_for_rule(db, user_id=user_id, rule_id=rule_id)
    finally:
        db.close()