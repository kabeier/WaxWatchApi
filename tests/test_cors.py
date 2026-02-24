from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def _build_cors_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "cors_allowed_origins", ["https://allowed.example"])
    monkeypatch.setattr(settings, "cors_allowed_methods", ["GET", "OPTIONS"])
    monkeypatch.setattr(settings, "cors_allowed_headers", ["Authorization", "Content-Type"])
    monkeypatch.setattr(settings, "cors_allow_credentials", True)

    app = create_app()
    return TestClient(app)


def test_cors_preflight_allows_configured_origin(monkeypatch):
    client = _build_cors_client(monkeypatch)

    response = client.options(
        "/healthz",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed.example"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_blocks_unconfigured_origin(monkeypatch):
    client = _build_cors_client(monkeypatch)

    response = client.options(
        "/healthz",
        headers={
            "Origin": "https://blocked.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
