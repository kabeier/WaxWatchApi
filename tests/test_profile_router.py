from __future__ import annotations


def test_get_me_returns_profile_and_integrations(client, user, headers, db_session):
    response = client.get("/api/me", headers=headers(user.id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(user.id)
    assert payload["email"] == user.email
    assert "integrations" in payload
    assert isinstance(payload["integrations"], list)


def test_patch_me_updates_display_name(client, user, headers, db_session):
    response = client.patch(
        "/api/me",
        headers=headers(user.id),
        json={"display_name": "Renamed User", "preferences": {"currency": "EUR"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "Renamed User"
    assert payload["preferences"]["currency"] == "EUR"


def test_logout_me_returns_marker(client, user, headers):
    response = client.post("/api/me/logout", headers=headers(user.id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["marker"]["user_id"] == str(user.id)


def test_deactivate_me_requires_no_active_rules(client, user, headers, db_session):
    from app.db import models

    db_session.add(
        models.WatchSearchRule(
            user_id=user.id,
            name="Has Active",
            query={"sources": ["discogs"]},
            poll_interval_seconds=600,
            is_active=True,
        )
    )
    db_session.flush()

    response = client.delete("/api/me", headers=headers(user.id))

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Cannot deactivate account while active watch rules exist"


def test_patch_me_validation_error_shape(client, user, headers):
    response = client.patch("/api/me", headers=headers(user.id), json={"display_name": ""})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["status"] == 422
    assert isinstance(payload["error"]["details"], list)
