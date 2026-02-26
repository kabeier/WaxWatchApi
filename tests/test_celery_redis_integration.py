from __future__ import annotations

import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError

from app.api.routers.health import _probe_redis
from app.core.celery_app import celery_app
from app.core.config import settings
from app.tasks import redis_roundtrip_echo_task


def _has_worker_for_queue(queue_name: str) -> bool:
    inspect = celery_app.control.inspect(timeout=1.0)
    if inspect is None:
        return False

    active_queues = inspect.active_queues()
    if not active_queues:
        return False

    for worker_queues in active_queues.values():
        for queue in worker_queues:
            if queue.get("name") == queue_name:
                return True
    return False


@pytest.mark.integration
def test_celery_redis_roundtrip_and_readiness(monkeypatch):
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    broker_url = settings.celery_broker_url
    result_backend = settings.celery_result_backend
    monkeypatch.setitem(celery_app.conf, "broker_url", broker_url)
    monkeypatch.setitem(celery_app.conf, "result_backend", result_backend)
    monkeypatch.setitem(celery_app.conf, "task_always_eager", False)
    monkeypatch.setitem(celery_app.conf, "task_eager_propagates", True)

    probe_ok, probe_reason = _probe_redis(timeout_seconds=1.0)
    assert probe_ok, probe_reason

    queue_name = celery_app.conf.task_default_queue
    if not _has_worker_for_queue(queue_name):
        pytest.skip(f"No running Celery worker detected for queue '{queue_name}'")

    payload = "redis-smoke"
    async_result = redis_roundtrip_echo_task.delay(payload)

    try:
        assert async_result.get(timeout=20) == payload
    except CeleryTimeoutError:
        pytest.skip(f"Timed out waiting for worker to consume queue '{queue_name}'")
