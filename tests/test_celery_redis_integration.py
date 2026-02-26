from __future__ import annotations

import pytest
from celery.contrib.testing.worker import start_worker

from app.api.routers.health import _probe_redis
from app.core.celery_app import celery_app
from app.core.config import settings
from app.tasks import redis_roundtrip_echo_task


@pytest.mark.integration
def test_celery_redis_roundtrip_and_readiness(monkeypatch):
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    broker_url = settings.celery_broker_url
    result_backend = settings.celery_result_backend
    monkeypatch.setitem(celery_app.conf, "broker_url", broker_url)
    monkeypatch.setitem(celery_app.conf, "result_backend", result_backend)
    monkeypatch.setitem(celery_app.conf, "task_always_eager", False)
    monkeypatch.setitem(celery_app.conf, "task_eager_propagates", True)

    celery_app.loader.import_default_modules()
    celery_app.loader.import_task_module("celery.contrib.testing.tasks")

    probe_ok, probe_reason = _probe_redis(timeout_seconds=1.0)
    assert probe_ok, probe_reason

    payload = "redis-smoke"
    with start_worker(
        celery_app,
        perform_ping_check=True,
        loglevel="WARNING",
        pool="solo",
        concurrency=1,
        queues=["waxwatch"],
    ):
        async_result = redis_roundtrip_echo_task.delay(payload)

        assert async_result.get(timeout=20) == payload
