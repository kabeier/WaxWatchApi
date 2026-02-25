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


def test_probe_db_returns_clear_failure_reason_on_sql_error(db_session, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from app.api.routers import health

    def _raise_sqlalchemy_error(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(health, "_run_with_timeout", _raise_sqlalchemy_error)

    ok, reason = health._probe_db(db_session, timeout_seconds=0.1)
    assert ok is False
    assert reason == "db readiness probe failed: SQLAlchemyError"


def test_metrics_endpoint_exposes_prometheus_payload(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "waxwatch_request_latency_seconds" in r.text
