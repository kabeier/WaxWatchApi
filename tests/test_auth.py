from __future__ import annotations

from uuid import uuid4


def test_requires_bearer_token(client):
    response = client.get("/api/events")
    assert response.status_code == 403


def test_rejects_x_user_id_header(client):
    response = client.get("/api/events", headers={"X-User-Id": str(uuid4())})
    assert response.status_code == 403


def test_rejects_expired_token(client, sign_jwt):
    token = sign_jwt(sub=str(uuid4()), exp_delta_seconds=-10)
    response = client.get("/api/events", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_rejects_wrong_issuer(client, sign_jwt):
    token = sign_jwt(sub=str(uuid4()), iss="https://example.com/auth/v1")
    response = client.get("/api/events", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_rejects_wrong_audience(client, sign_jwt):
    token = sign_jwt(sub=str(uuid4()), aud="not-authenticated")
    response = client.get("/api/events", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
