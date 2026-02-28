from __future__ import annotations

import logging
from uuid import uuid4

import jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app


def test_auth_invalid_algorithm_logs_warning(client, caplog):
    token = jwt.encode({"sub": str(uuid4())}, "sensitive-token", algorithm="HS256", headers={"kid": "bad"})

    with caplog.at_level(logging.WARNING, logger="app.auth"):
        response = client.get("/api/events", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    warning = next(record for record in caplog.records if record.message == "auth.token.invalid_algorithm")
    assert warning.levelname == "WARNING"
    assert warning.alg == "HS256"
    assert "sensitive-token" not in caplog.text


def test_admin_denial_logs_warning(client, user, headers, caplog):
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        response = client.get("/api/provider-requests/admin", headers=headers(user.id))

    assert response.status_code == 403
    warning = next(record for record in caplog.records if record.message == "auth.admin.denied")
    assert warning.levelname == "WARNING"
    assert warning.user_id == str(user.id)


def test_http_exception_and_validation_logs_include_request_context(caplog):
    app = create_app()

    @app.get("/boom")
    def _boom():
        raise HTTPException(status_code=500, detail="boom")

    with TestClient(app) as local_client:
        with caplog.at_level(logging.INFO, logger="app.main"):
            boom_response = local_client.get("/boom")
            invalid_response = local_client.get(
                "/api/watch-rules", headers={"Authorization": "Bearer bad-token"}
            )

    assert boom_response.status_code == 500
    assert invalid_response.status_code == 401

    server_error = next(record for record in caplog.records if record.message == "http.exception.server")
    assert server_error.request_id
    assert server_error.method == "GET"
    assert server_error.path == "/boom"
    assert server_error.status_code == 500
    assert server_error.internal_error_code == "http_error"

    auth_error = next(record for record in caplog.records if record.message == "http.exception.auth")
    assert auth_error.path == "/api/watch-rules"
    assert auth_error.status_code == 401
