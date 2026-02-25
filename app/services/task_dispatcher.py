from __future__ import annotations


def enqueue_notification_delivery(notification_id: str) -> None:
    from app.tasks import deliver_notification_task

    deliver_notification_task.delay(notification_id)
