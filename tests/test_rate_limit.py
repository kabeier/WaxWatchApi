from __future__ import annotations

from fastapi import Request

from app.core.config import settings
from app.core.rate_limit import reset_rate_limiter_state
from app.main import create_app


def test_rate_limit_exceeded_returns_consistent_error_envelope(client, user, headers, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_watch_rules_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_watch_rules_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_burst", 0)
    reset_rate_limiter_state()

    auth_headers = headers(user.id)

    first = client.get("/api/watch-rules", headers=auth_headers)
    assert first.status_code == 200

    second = client.get("/api/watch-rules", headers=auth_headers)
    assert second.status_code == 429
    payload = second.json()["error"]
    assert payload["message"] == "rate limit exceeded"
    assert payload["code"] == "rate_limited"
    assert payload["status"] == 429
    assert payload["details"]["scope"] == "watch_rules"
    assert second.headers.get("retry-after")


def test_global_anonymous_limit_applies_but_healthz_is_exempt(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_global_anonymous_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_global_anonymous_burst", 0)
    reset_rate_limiter_state()

    app = create_app()

    @app.get("/api/public-rate-limit-probe")
    def public_probe(_request: Request):
        return {"ok": True}

    from fastapi.testclient import TestClient

    with TestClient(app) as local_client:
        first = local_client.get("/api/public-rate-limit-probe")
        assert first.status_code == 200

        second = local_client.get("/api/public-rate-limit-probe")
        assert second.status_code == 429

        health_first = local_client.get("/healthz")
        health_second = local_client.get("/healthz")
        assert health_first.status_code == 200
        assert health_second.status_code == 200
