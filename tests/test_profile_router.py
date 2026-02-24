from __future__ import annotations

from app.db import models


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


def test_deactivate_me_auto_disables_rules_and_blocks_auth(client, user, headers, db_session):
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

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["deactivated_at"]

    disabled_rule = (
        db_session.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.user_id == user.id)
        .one()
    )
    assert disabled_rule.is_active is False

    follow_up = client.get("/api/me", headers=headers(user.id))
    assert follow_up.status_code == 403
    assert follow_up.json()["error"]["message"] == "User account is inactive"


def test_hard_delete_me_cascades_related_entities_and_blocks_access(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Hard Delete Rule",
        query={"sources": ["discogs"]},
        poll_interval_seconds=600,
        is_active=True,
    )
    db_session.add(rule)
    db_session.flush()

    event = models.Event(user_id=user.id, type=models.EventType.RULE_CREATED, rule_id=rule.id)
    db_session.add(event)
    db_session.flush()

    db_session.add(
        models.Notification(
            user_id=user.id,
            event_id=event.id,
            event_type=models.EventType.RULE_CREATED,
            channel=models.NotificationChannel.realtime,
            status=models.NotificationStatus.pending,
        )
    )
    db_session.add(
        models.ExternalAccountLink(
            user_id=user.id,
            provider=models.Provider.discogs,
            external_user_id="discogs-123",
        )
    )
    db_session.add(
        models.ImportJob(
            user_id=user.id,
            provider=models.Provider.discogs,
            import_scope="collection",
            status="pending",
        )
    )
    db_session.add(
        models.ProviderRequest(
            user_id=user.id,
            provider=models.Provider.discogs,
            endpoint="/releases/1",
            method="GET",
        )
    )
    db_session.flush()

    response = client.delete("/api/me/hard-delete", headers=headers(user.id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["deleted_at"]

    assert db_session.query(models.User).filter(models.User.id == user.id).count() == 0
    assert db_session.query(models.WatchSearchRule).filter(models.WatchSearchRule.user_id == user.id).count() == 0
    assert db_session.query(models.Event).filter(models.Event.user_id == user.id).count() == 0
    assert db_session.query(models.Notification).filter(models.Notification.user_id == user.id).count() == 0
    assert db_session.query(models.ExternalAccountLink).filter(models.ExternalAccountLink.user_id == user.id).count() == 0
    assert db_session.query(models.ImportJob).filter(models.ImportJob.user_id == user.id).count() == 0
    assert db_session.query(models.ProviderRequest).filter(models.ProviderRequest.user_id == user.id).count() == 0

    follow_up = client.get("/api/me", headers=headers(user.id))
    assert follow_up.status_code == 404
    assert follow_up.json()["error"]["message"] == "User profile not found"


def test_patch_me_validation_error_shape(client, user, headers):
    response = client.patch("/api/me", headers=headers(user.id), json={"display_name": ""})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["status"] == 422
    assert isinstance(payload["error"]["details"], list)
