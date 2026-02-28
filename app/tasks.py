from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.logging import get_logger
from app.db import models
from app.db.base import SessionLocal
from app.services.backfill import backfill_matches_for_rule
from app.services.discogs_import import discogs_import_service
from app.services.notifications import defer_delivery_seconds, publish_realtime, send_email
from app.services.scheduler import run_due_rules_once

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.redis_roundtrip_echo")
def redis_roundtrip_echo_task(payload: str) -> str:
    return payload


@celery_app.task(name="app.tasks.backfill_rule_matches")
def backfill_rule_matches_task(user_id: str, rule_id: str) -> None:
    db = SessionLocal()
    try:
        backfill_matches_for_rule(db, user_id=UUID(user_id), rule_id=UUID(rule_id))
        db.commit()
    except Exception:
        logger.exception(
            "tasks.backfill_rule_matches.failed",
            extra={
                "task_name": "backfill_rule_matches_task",
                "user_id": user_id,
                "rule_id": rule_id,
            },
        )
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
        logger.exception(
            "tasks.poll_due_rules.failed",
            extra={
                "task_name": "poll_due_rules_task",
                "scheduler_batch_size": settings.scheduler_batch_size,
                "scheduler_rule_limit": settings.scheduler_rule_limit,
            },
        )
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.sync_discogs_lists")
def sync_discogs_lists_task() -> dict[str, int]:
    if not settings.discogs_sync_enabled:
        return {"discovered_users": 0, "enqueued_jobs": 0, "reused_jobs": 0, "disabled": 1}

    db = SessionLocal()
    try:
        links = discogs_import_service.list_sync_candidates(
            db,
            limit=settings.discogs_sync_user_batch_size,
        )

        enqueued_jobs = 0
        reused_jobs = 0
        queued_jobs: list[tuple[str, int]] = []
        for link in links:
            job, created = discogs_import_service.ensure_import_job(
                db,
                user_id=link.user_id,
                source="both",
                cooldown_seconds=settings.discogs_sync_interval_seconds,
            )
            if created:
                countdown = random.randint(0, max(settings.discogs_sync_jitter_seconds, 0))
                countdown += random.randint(0, max(settings.discogs_sync_spread_seconds, 0))
                queued_jobs.append((str(job.id), countdown))
                enqueued_jobs += 1
            else:
                reused_jobs += 1

        db.commit()
        for job_id, countdown in queued_jobs:
            run_discogs_import_task.apply_async(args=[job_id], countdown=countdown)
        return {
            "discovered_users": len(links),
            "enqueued_jobs": enqueued_jobs,
            "reused_jobs": reused_jobs,
            "disabled": 0,
        }
    except Exception:
        logger.exception(
            "tasks.sync_discogs_lists.failed",
            extra={
                "task_name": "sync_discogs_lists_task",
                "discovered_users": len(links) if "links" in locals() else 0,
                "enqueued_jobs": enqueued_jobs if "enqueued_jobs" in locals() else 0,
                "reused_jobs": reused_jobs if "reused_jobs" in locals() else 0,
            },
        )
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
        logger.exception(
            "tasks.run_discogs_import.failed",
            extra={
                "task_name": "run_discogs_import_task",
                "job_id": job_id,
            },
        )
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
        if notification is None:
            logger.warning(
                "notifications.delivery.notification_not_found",
                extra={
                    "notification_id": notification_id,
                    "likely_race": True,
                },
            )
            return

        if notification.status == models.NotificationStatus.sent:
            return

        defer_seconds = defer_delivery_seconds(db, notification=notification)
        if defer_seconds is not None:
            if not self.request.is_eager:
                deliver_notification_task.apply_async(args=[notification_id], countdown=defer_seconds)
            db.commit()
            return

        if notification.channel == models.NotificationChannel.email:
            send_email(db, notification=notification)
        elif notification.channel == models.NotificationChannel.realtime:
            asyncio.run(publish_realtime(db, notification=notification))
        else:
            raise RuntimeError(f"unsupported notification channel: {notification.channel}")

        db.commit()
    except RuntimeError:
        db.commit()
        logger.warning(
            "notifications.delivery.retry",
            extra={
                "task_name": "deliver_notification_task",
                "notification_id": notification_id,
                "at": datetime.now(timezone.utc).isoformat(),
                "retry_count": self.request.retries,
                "retry_backoff_seconds": settings.celery_task_retry_backoff_seconds,
                "max_retries": settings.celery_task_max_retries,
            },
        )
        raise
    except Exception:
        logger.exception(
            "tasks.deliver_notification.failed",
            extra={
                "task_name": "deliver_notification_task",
                "notification_id": notification_id,
                "retry_count": self.request.retries,
                "retry_backoff_seconds": settings.celery_task_retry_backoff_seconds,
                "max_retries": settings.celery_task_max_retries,
            },
        )
        db.rollback()
        raise
    finally:
        db.close()
