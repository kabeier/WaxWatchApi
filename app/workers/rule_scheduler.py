from __future__ import annotations

import time

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.base import SessionLocal
from app.services.scheduler import run_due_rules_once

logger = get_logger(__name__)


def run_forever() -> None:
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)

    while True:
        db = SessionLocal()
        try:
            result = run_due_rules_once(
                db,
                batch_size=settings.scheduler_batch_size,
                rule_limit=settings.scheduler_rule_limit,
            )
            db.commit()
            logger.info(
                "scheduler.tick",
                extra={
                    "processed_rules": result.processed_rules,
                    "failed_rules": result.failed_rules,
                    "poll_interval_seconds": settings.scheduler_poll_interval_seconds,
                },
            )
        except Exception:
            db.rollback()
            logger.exception("scheduler.tick_failed")
        finally:
            db.close()

        time.sleep(settings.scheduler_poll_interval_seconds)


if __name__ == "__main__":
    run_forever()
