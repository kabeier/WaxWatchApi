from __future__ import annotations


def enqueue_notification_delivery(notification_id: str, *, countdown: int | None = None) -> None:
    from app.tasks import deliver_notification_task

    if countdown is not None:
        deliver_notification_task.apply_async(args=[notification_id], countdown=countdown)
        return

    deliver_notification_task.delay(notification_id)
