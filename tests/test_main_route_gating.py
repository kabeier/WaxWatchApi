from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


@pytest.mark.parametrize("environment", ["prod", "production", "staging"])
def test_dev_routes_unavailable_for_production_like_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str
):
    monkeypatch.setattr(settings, "environment", environment)
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/dev/listings/ingest")

    assert response.status_code == 404


@pytest.mark.parametrize("environment", ["dev", "test", "local"])
def test_dev_routes_available_only_for_allowlisted_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str
):
    monkeypatch.setattr(settings, "environment", environment)
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/dev/listings/ingest")

    assert response.status_code != 404
