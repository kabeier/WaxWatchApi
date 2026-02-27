from __future__ import annotations

from fastapi import Depends, Request

from app.api.deps import rate_limit_scope
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


def test_high_risk_search_scope_is_throttled(client, user, headers, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_search_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_search_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_burst", 0)
    reset_rate_limiter_state()

    auth_headers = headers(user.id)
    payload = {
        "name": "house alerts",
        "query": {"keywords": ["house"], "providers": ["mock"]},
        "poll_interval_seconds": 600,
    }

    first = client.post("/api/search/save-alert", headers=auth_headers, json=payload)
    assert first.status_code == 200

    second = client.post("/api/search/save-alert", headers=auth_headers, json=payload)
    assert second.status_code == 429
    assert second.json()["error"]["details"]["scope"] == "search"


def test_high_risk_discogs_scope_is_throttled(client, user, headers, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_discogs_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_discogs_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_burst", 0)
    reset_rate_limiter_state()

    auth_headers = headers(user.id)

    first = client.get("/api/integrations/discogs/status", headers=auth_headers)
    assert first.status_code == 200

    second = client.get("/api/integrations/discogs/status", headers=auth_headers)
    assert second.status_code == 429
    assert second.json()["error"]["details"]["scope"] == "discogs"


def test_stream_events_scope_is_throttled(client, user, headers, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_stream_events_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_stream_events_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_burst", 0)
    reset_rate_limiter_state()

    app = create_app()

    @app.get(
        "/api/stream-rate-limit-probe",
        dependencies=[Depends(rate_limit_scope("stream_events", require_authenticated_principal=True))],
    )
    def stream_probe():
        return {"ok": True}

    from fastapi.testclient import TestClient

    with TestClient(app) as local_client:
        auth_headers = headers(user.id)

        first = local_client.get("/api/stream-rate-limit-probe", headers=auth_headers)
        assert first.status_code == 200

        second = local_client.get("/api/stream-rate-limit-probe", headers=auth_headers)
        assert second.status_code == 429
        assert second.json()["error"]["details"]["scope"] == "stream_events"


def test_search_scope_tracks_unauthenticated_requests_and_throttles(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_search_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_search_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_anonymous_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_anonymous_burst", 0)
    reset_rate_limiter_state()

    payload = {
        "name": "house alerts",
        "query": {"keywords": ["house"], "providers": ["mock"]},
        "poll_interval_seconds": 600,
    }

    first = client.post("/api/search/save-alert", json=payload)
    assert first.status_code == 401

    second = client.post("/api/search/save-alert", json=payload)
    assert second.status_code == 429
    assert second.json()["error"]["details"]["scope"] == "search"


def test_watch_rules_scope_tracks_unauthenticated_requests_and_throttles(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_watch_rules_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_watch_rules_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_anonymous_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_anonymous_burst", 0)
    reset_rate_limiter_state()

    first = client.get("/api/watch-rules")
    assert first.status_code == 401

    second = client.get("/api/watch-rules")
    assert second.status_code == 429
    assert second.json()["error"]["details"]["scope"] == "watch_rules"


def test_rate_limiting_can_be_disabled_for_non_throttled_behavior(client, user, headers, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_watch_rules_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_watch_rules_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_burst", 0)
    reset_rate_limiter_state()

    auth_headers = headers(user.id)
    first = client.get("/api/watch-rules", headers=auth_headers)
    second = client.get("/api/watch-rules", headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200


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
