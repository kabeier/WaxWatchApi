from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "waxwatch",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_default_queue="waxwatch",
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery_worker_max_tasks_per_child,
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_eager_propagates,
    beat_schedule={
        "poll-due-rules": {
            "task": "app.tasks.poll_due_rules",
            "schedule": max(settings.scheduler_poll_interval_seconds, 1),
            "options": {"expires": max(settings.scheduler_poll_interval_seconds - 1, 1)},
        },
        "sync-discogs-lists": {
            "task": "app.tasks.sync_discogs_lists",
            "schedule": max(settings.discogs_sync_interval_seconds, 60),
            "options": {"expires": max(settings.discogs_sync_interval_seconds - 1, 1)},
        },
    },
)

celery_app.autodiscover_tasks(["app"])
