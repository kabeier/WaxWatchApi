from __future__ import annotations

from fastapi import Depends, Request
from starlette.datastructures import Address

from app.api.deps import rate_limit_scope
from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import (
    _client_identifier,
    _token_fingerprint,
    enforce_global_rate_limit,
    reset_rate_limiter_state,
)
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


def test_search_scope_bogus_bearer_tokens_share_budget_for_auth_required_scope(client, monkeypatch):
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

    first = client.post(
        "/api/search/save-alert",
        json=payload,
        headers={"Authorization": "Bearer bogus-token-1"},
    )
    assert first.status_code == 401

    second = client.post(
        "/api/search/save-alert",
        json=payload,
        headers={"Authorization": "Bearer bogus-token-2"},
    )
    assert second.status_code == 429
    assert second.json()["error"]["details"]["scope"] == "search"


def test_search_scope_valid_bearer_tokens_preserve_shared_budget(client, user, headers, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_search_rpm", 1)
    monkeypatch.setattr(settings, "rate_limit_search_burst", 0)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_rpm", 100)
    monkeypatch.setattr(settings, "rate_limit_global_authenticated_burst", 0)
    reset_rate_limiter_state()

    payload = {
        "name": "house alerts",
        "query": {"keywords": ["house"], "providers": ["mock"]},
        "poll_interval_seconds": 600,
    }

    first = client.post("/api/search/save-alert", headers=headers(user.id), json=payload)
    assert first.status_code == 200

    second = client.post("/api/search/save-alert", headers=headers(user.id), json=payload)
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


def test_rate_limit_helpers_cover_forwarded_for_and_empty_bearer_header():
    forwarded_request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/api/probe",
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
            "query_string": b"",
            "client": Address("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
    )

    unknown_client_request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/api/probe",
            "headers": [(b"authorization", b"Bearer   ")],
            "query_string": b"",
            "client": None,
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
    )

    assert _client_identifier(forwarded_request) == "203.0.113.9"
    assert _client_identifier(unknown_client_request) == "unknown"
    assert _token_fingerprint(unknown_client_request) is None


def test_enforce_global_rate_limit_uses_authenticated_scope_with_bearer(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    captured: list[tuple[str, bool]] = []

    def _capture(request: Request, *, scope, require_authenticated_principal=False):
        captured.append((scope, require_authenticated_principal))

    monkeypatch.setattr(rate_limit, "enforce_rate_limit", _capture)

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/api/probe",
            "headers": [(b"authorization", b"Bearer token-value")],
            "query_string": b"",
            "client": Address("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
    )

    enforce_global_rate_limit(request)

    assert captured == [("global_authenticated", True)]


def test_enforce_global_rate_limit_uses_anonymous_scope_without_bearer(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    captured: list[tuple[str, bool]] = []

    def _capture(request: Request, *, scope, require_authenticated_principal=False):
        captured.append((scope, require_authenticated_principal))

    monkeypatch.setattr(rate_limit, "enforce_rate_limit", _capture)

    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/api/probe",
            "headers": [],
            "query_string": b"",
            "client": Address("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
    )

    enforce_global_rate_limit(request)

    assert captured == [("global_anonymous", False)]


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
