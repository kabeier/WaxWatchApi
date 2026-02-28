from __future__ import annotations


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["db"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "skipped"


def test_readyz_returns_503_when_db_probe_fails(client, monkeypatch):
    from app.api.routers import health

    def _fail_db(*_args, **_kwargs):
        return False, "db readiness probe failed: SQLAlchemyError"

    monkeypatch.setattr(health, "_probe_db", _fail_db)

    r = client.get("/readyz")
    assert r.status_code == 503
    payload = r.json()["error"]["details"]
    assert payload["status"] == "not_ready"
    assert payload["checks"]["db"] == {
        "status": "failed",
        "reason": "db readiness probe failed: SQLAlchemyError",
    }


def test_readyz_returns_503_when_redis_required_and_unavailable(client, monkeypatch):
    from app.api.routers import health

    monkeypatch.setattr(health, "_redis_required", lambda: True)
    monkeypatch.setattr(
        health, "_probe_redis", lambda **_kwargs: (False, "redis readiness probe failed: ConnectionError")
    )

    r = client.get("/readyz")
    assert r.status_code == 503
    payload = r.json()["error"]["details"]
    assert payload["status"] == "not_ready"
    assert payload["checks"]["redis"] == {
        "status": "failed",
        "reason": "redis readiness probe failed: ConnectionError",
    }


def test_readyz_db_probe_does_not_use_worker_thread(client, monkeypatch):
    from app.api.routers import health

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("_run_with_timeout should not be used by _probe_db")

    monkeypatch.setattr(health, "_run_with_timeout", _raise_if_called)

    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["checks"]["db"]["status"] == "ok"


def test_probe_db_returns_clear_failure_reason_on_sql_error():
    from sqlalchemy.exc import SQLAlchemyError

    from app.api.routers import health

    class _DB:
        def get_bind(self):
            raise SQLAlchemyError("boom")

    ok, reason = health._probe_db(_DB(), timeout_seconds=0.1)
    assert ok is False
    assert reason == "db readiness probe failed: SQLAlchemyError"


def test_probe_db_handles_connection_bound_bind_without_connect():
    from app.api.routers import health

    calls: list[str] = []

    class _Connection:
        class dialect:  # noqa: D106
            name = "sqlite"

        def in_transaction(self):
            return True

        def execute(self, stmt, params=None):
            calls.append(str(stmt))

    class _DB:
        def get_bind(self):
            return _Connection()

    ok, reason = health._probe_db(_DB(), timeout_seconds=0.25)

    assert ok is True
    assert reason is None
    assert calls == ["SELECT 1"]


def test_probe_db_uses_local_statement_timeout_for_postgres():
    from app.api.routers import health

    calls: list[tuple[str, dict[str, str] | None]] = []

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def begin(self):
            return self

        def execute(self, stmt, params=None):
            calls.append((str(stmt), params))

    class _Bind:
        class dialect:  # noqa: D106
            name = "postgresql"

        def connect(self):
            return _Connection()

    class _DB:
        def get_bind(self):
            return _Bind()

    ok, reason = health._probe_db(_DB(), timeout_seconds=0.25)

    assert ok is True
    assert reason is None
    assert calls == [
        ("SET LOCAL statement_timeout = :timeout", {"timeout": "250ms"}),
        ("SELECT 1", None),
    ]


def test_metrics_endpoint_exposes_prometheus_payload(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "waxwatch_request_latency_seconds" in r.text
    assert "waxwatch_scheduler_lag_seconds" in r.text
    assert "waxwatch_provider_failures_total" in r.text
    assert "waxwatch_db_connection_utilization" in r.text


def test_record_db_pool_utilization_sets_ratio(monkeypatch):
    from app.api.routers import health

    calls: list[float] = []

    class _Pool:
        def checkedout(self):
            return 3

        def size(self):
            return 10

    class _Bind:
        pool = _Pool()

    class _DB:
        def get_bind(self):
            return _Bind()

    monkeypatch.setattr(
        health, "set_db_connection_utilization", lambda *, utilization_ratio: calls.append(utilization_ratio)
    )

    health._record_db_pool_utilization(_DB())

    assert calls == [0.3]


def test_record_db_pool_utilization_skips_when_pool_size_non_positive(monkeypatch):
    from app.api.routers import health

    calls: list[float] = []

    class _Pool:
        def checkedout(self):
            return 1

        def size(self):
            return 0

    class _Bind:
        pool = _Pool()

    class _DB:
        def get_bind(self):
            return _Bind()

    monkeypatch.setattr(
        health, "set_db_connection_utilization", lambda *, utilization_ratio: calls.append(utilization_ratio)
    )

    health._record_db_pool_utilization(_DB())

    assert calls == []


def test_record_db_pool_utilization_skips_when_pool_api_missing(monkeypatch):
    from app.api.routers import health

    calls: list[float] = []

    class _Pool:
        pass

    class _Bind:
        pool = _Pool()

    class _DB:
        def get_bind(self):
            return _Bind()

    monkeypatch.setattr(
        health, "set_db_connection_utilization", lambda *, utilization_ratio: calls.append(utilization_ratio)
    )

    health._record_db_pool_utilization(_DB())

    assert calls == []
