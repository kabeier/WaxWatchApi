from __future__ import annotations

import multiprocessing
import time

import pytest

from app.api.routers.health import _probe_redis
from app.core.celery_app import celery_app
from app.core.config import settings
from app.tasks import redis_roundtrip_echo_task


def _run_test_worker() -> None:
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=WARNING",
            "--pool=solo",
            "--concurrency=1",
            "--queues=waxwatch",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
        ]
    )


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

    worker = multiprocessing.Process(target=_run_test_worker)
    worker.start()
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if celery_app.control.ping(timeout=1):
                break
            time.sleep(0.5)
        else:
            pytest.fail("celery worker did not become ready")

        payload = "redis-smoke"
        async_result = redis_roundtrip_echo_task.delay(payload)

        assert async_result.get(timeout=20) == payload
    finally:
        worker.terminate()
        worker.join(timeout=10)
