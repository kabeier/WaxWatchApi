from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db import models
from app.db.base import SessionLocal
from app.services.backfill import backfill_matches_for_rule
from app.services.discogs_import import discogs_import_service
from app.services.notifications import publish_realtime, send_email
from app.services.scheduler import run_due_rules_once

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.backfill_rule_matches")
def backfill_rule_matches_task(user_id: str, rule_id: str) -> None:
    db = SessionLocal()
    try:
        backfill_matches_for_rule(db, user_id=UUID(user_id), rule_id=UUID(rule_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.poll_due_rules")
def poll_due_rules_task() -> dict[str, int]:
    db = SessionLocal()
    try:
        result = run_due_rules_once(
            db,
            batch_size=settings.scheduler_batch_size,
            rule_limit=settings.scheduler_rule_limit,
        )
        db.commit()
        return {"processed_rules": result.processed_rules, "failed_rules": result.failed_rules}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_discogs_import")
def run_discogs_import_task(job_id: str) -> None:
    db = SessionLocal()
    try:
        discogs_import_service.execute_import_job(db, job_id=UUID(job_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.tasks.deliver_notification",
    autoretry_for=(RuntimeError,),
    retry_backoff=settings.celery_task_retry_backoff_seconds,
    retry_kwargs={"max_retries": settings.celery_task_max_retries},
)
def deliver_notification_task(self, notification_id: str) -> None:
    db = SessionLocal()
    try:
        notification = (
            db.query(models.Notification)
            .filter(models.Notification.id == UUID(notification_id))
            .one_or_none()
        )
        if notification is None or notification.status == models.NotificationStatus.sent:
            return

        if notification.channel == models.NotificationChannel.email:
            send_email(db, notification=notification)
        elif notification.channel == models.NotificationChannel.realtime:
            asyncio.run(publish_realtime(db, notification=notification))
        else:
            raise RuntimeError(f"unsupported notification channel: {notification.channel}")

        db.commit()
    except RuntimeError:
        db.rollback()
        logger.warning(
            "notifications.delivery.retry",
            extra={"notification_id": notification_id, "at": datetime.now(timezone.utc).isoformat()},
        )
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
