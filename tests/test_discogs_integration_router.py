from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.db import models
from app.services.discogs_import import discogs_import_service


def test_discogs_oauth_connect_success(client, user, headers, db_session, monkeypatch):
    h = headers(user.id)

    start = client.post(
        "/api/integrations/discogs/oauth/start",
        json={"scopes": ["identity", "wantlist"]},
        headers=h,
    )
    assert start.status_code == 200, start.text
    start_body = start.json()
    assert start_body["provider"] == "discogs"
    assert "state" in start_body
    assert "authorize_url" in start_body

    def _fake_post(url, data, timeout):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "access_token": "oauth-token",
                    "refresh_token": "refresh-token",
                    "scope": "identity wantlist",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }

        return _Resp()

    def _fake_get(url, headers, timeout):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"username": "discogs-user"}

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.post", _fake_post)
    monkeypatch.setattr("app.services.discogs_import.httpx.get", _fake_get)

    callback = client.post(
        "/api/integrations/discogs/oauth/callback",
        json={"state": start_body["state"], "code": "auth-code"},
        headers=h,
    )
    assert callback.status_code == 200, callback.text
    body = callback.json()
    assert body["connected"] is True
    assert body["external_user_id"] == "discogs-user"

    status = client.get("/api/integrations/discogs/status", headers=h)
    assert status.status_code == 200, status.text
    assert status.json()["connected"] is True

    link = db_session.query(models.ExternalAccountLink).filter_by(user_id=user.id).one()
    assert link.access_token is not None
    assert link.access_token.startswith("enc:v1:")
    assert link.token_metadata["oauth_connected"] is True
    assert link.token_metadata["oauth_state"] is None
    assert link.refresh_token == "refresh-token"
    assert link.token_type == "Bearer"
    assert link.scopes == ["identity", "wantlist"]
    assert link.access_token_expires_at is not None


def test_discogs_oauth_callback_invalid_state(client, user, headers):
    h = headers(user.id)
    start = client.post("/api/integrations/discogs/oauth/start", json={}, headers=h)
    assert start.status_code == 200, start.text

    callback = client.post(
        "/api/integrations/discogs/oauth/callback",
        json={"state": "bad-state", "code": "auth-code"},
        headers=h,
    )
    assert callback.status_code == 400, callback.text
    assert callback.json()["error"]["message"] == "Invalid OAuth state"


def test_discogs_oauth_reconnect_reuses_link(client, user, headers, db_session, monkeypatch):
    h = headers(user.id)

    def _fake_post(url, data, timeout):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "access_token": f"token-{data['code']}",
                    "scope": "identity",
                    "token_type": "Bearer",
                }

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.post", _fake_post)

    usernames = ["first-user", "second-user"]

    def _fake_get(url, headers, timeout):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"username": usernames.pop(0)}

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.get", _fake_get)

    first_start = client.post("/api/integrations/discogs/oauth/start", json={}, headers=h)
    first_state = first_start.json()["state"]
    first_callback = client.post(
        "/api/integrations/discogs/oauth/callback",
        json={"state": first_state, "code": "one"},
        headers=h,
    )
    assert first_callback.status_code == 200, first_callback.text

    second_start = client.post("/api/integrations/discogs/oauth/start", json={}, headers=h)
    second_state = second_start.json()["state"]
    second_callback = client.post(
        "/api/integrations/discogs/oauth/callback",
        json={"state": second_state, "code": "two"},
        headers=h,
    )
    assert second_callback.status_code == 200, second_callback.text

    links = db_session.query(models.ExternalAccountLink).filter_by(user_id=user.id).all()
    assert len(links) == 1
    assert links[0].external_user_id == "second-user"
    assert links[0].access_token is not None
    assert links[0].access_token.startswith("enc:v1:")


def test_discogs_disconnect_removes_link(client, user, headers, db_session, monkeypatch):
    h = headers(user.id)
    now = datetime.now(timezone.utc)
    link = models.ExternalAccountLink(
        user_id=user.id,
        provider=models.Provider.discogs,
        external_user_id="discogs-user",
        access_token="old-token",
        token_metadata={"oauth_connected": True},
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(link)
    db_session.flush()

    def _fake_post(url, data, timeout):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {}

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.post", _fake_post)

    disconnect = client.post("/api/integrations/discogs/disconnect", json={"revoke": True}, headers=h)
    assert disconnect.status_code == 200, disconnect.text
    assert disconnect.json()["disconnected"] is True

    assert db_session.query(models.ExternalAccountLink).filter_by(user_id=user.id).count() == 0
    status = client.get("/api/integrations/discogs/status", headers=h)
    assert status.json()["connected"] is False


def test_discogs_import_and_job_status(client, user, headers, db_session, monkeypatch):
    h = headers(user.id)
    client.post(
        "/api/integrations/discogs/connect",
        json={
            "external_user_id": "discogs-user",
            "access_token": "token",
            "token_metadata": {
                "refresh_token": "manual-refresh",
                "token_type": "Bearer",
                "scope": "identity collection",
                "expires_at": "2030-01-01T00:00:00+00:00",
            },
        },
        headers=h,
    )

    def _fake_get(url, headers, params, timeout):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                if url.endswith("/wants"):
                    return {
                        "pagination": {"page": 1, "pages": 1},
                        "wants": [
                            {
                                "id": 1001,
                                "basic_information": {
                                    "id": 1001,
                                    "title": "Demo Want",
                                    "year": 1999,
                                    "master_id": 5001,
                                    "artists": [{"name": "Artist A"}],
                                },
                            }
                        ],
                    }
                return {
                    "pagination": {"page": 1, "pages": 1},
                    "releases": [
                        {
                            "id": 1002,
                            "basic_information": {
                                "id": 1002,
                                "title": "Demo Collection",
                                "year": 2001,
                                "master_id": 5002,
                                "artists": [{"name": "Artist B"}],
                            },
                        }
                    ],
                }

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.get", _fake_get)
    monkeypatch.setattr(
        "app.api.routers.discogs.run_discogs_import_task.delay",
        lambda job_id: discogs_import_service.execute_import_job(db_session, job_id=UUID(job_id)),
    )

    run_import = client.post("/api/integrations/discogs/import", json={"source": "both"}, headers=h)
    assert run_import.status_code == 200, run_import.text
    import_body = run_import.json()
    assert import_body["status"] == "completed"
    assert import_body["processed_count"] == 2
    assert import_body["created_count"] == 2

    job_id = import_body["id"]
    job_status = client.get(f"/api/integrations/discogs/import/{job_id}", headers=h)
    assert job_status.status_code == 200, job_status.text
    assert job_status.json()["status"] == "completed"

    link = db_session.query(models.ExternalAccountLink).filter_by(user_id=user.id).one()
    assert link.refresh_token == "manual-refresh"
    assert link.token_type == "Bearer"
    assert link.scopes == ["identity", "collection"]
    assert link.access_token_expires_at is not None

    releases = db_session.query(models.WatchRelease).filter_by(user_id=user.id).all()
    assert len(releases) == 2
    assert {release.discogs_master_id for release in releases} == {5001, 5002}
    assert {release.match_mode for release in releases} == {"exact_release"}

    release_by_id = {release.discogs_release_id: release for release in releases}
    assert release_by_id[1001].imported_from_wantlist is True
    assert release_by_id[1001].imported_from_collection is False
    assert release_by_id[1002].imported_from_collection is True
    assert release_by_id[1002].imported_from_wantlist is False

    event_types = [
        ev.type.value
        for ev in db_session.query(models.Event)
        .filter(models.Event.user_id == user.id)
        .order_by(models.Event.created_at.asc())
        .all()
    ]
    assert "IMPORT_STARTED" in event_types
    assert "IMPORT_COMPLETED" in event_types


def test_discogs_import_failure_persists_job_and_event(client, user, headers, db_session, monkeypatch):
    h = headers(user.id)
    client.post(
        "/api/integrations/discogs/connect",
        json={
            "external_user_id": "discogs-user",
            "access_token": "token",
            "token_metadata": {
                "refresh_token": "manual-refresh",
                "token_type": "Bearer",
                "scope": "identity collection",
                "expires_at": "2030-01-01T00:00:00+00:00",
            },
        },
        headers=h,
    )

    def _fake_get(url, headers, params, timeout):
        class _Resp:
            status_code = 500

            @staticmethod
            def json():
                return {"error": "boom"}

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.get", _fake_get)
    monkeypatch.setattr(
        "app.api.routers.discogs.run_discogs_import_task.delay",
        lambda job_id: discogs_import_service.execute_import_job(db_session, job_id=UUID(job_id)),
    )

    run_import = client.post("/api/integrations/discogs/import", json={"source": "wantlist"}, headers=h)
    assert run_import.status_code == 200, run_import.text
    import_body = run_import.json()
    assert import_body["status"] == "failed"
    assert import_body["error_count"] == 1
    assert import_body["errors"]

    job_id = import_body["id"]
    job_status = client.get(f"/api/integrations/discogs/import/{job_id}", headers=h)
    assert job_status.status_code == 200, job_status.text
    assert job_status.json()["status"] == "failed"

    event_types = [
        ev.type.value
        for ev in db_session.query(models.Event)
        .filter(models.Event.user_id == user.id)
        .order_by(models.Event.created_at.asc())
        .all()
    ]
    assert "IMPORT_STARTED" in event_types
    assert "IMPORT_FAILED" in event_types


def test_discogs_imported_items_list_and_open_in_discogs(client, user, headers, db_session):
    h = headers(user.id)
    now = datetime.now(timezone.utc)

    want_only = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=1001,
        discogs_master_id=5001,
        match_mode="exact_release",
        title="Want Release",
        artist="Artist W",
        year=1999,
        currency="USD",
        is_active=True,
        imported_from_wantlist=True,
        imported_from_collection=False,
        created_at=now,
        updated_at=now,
    )
    both_sources = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=1002,
        discogs_master_id=5002,
        match_mode="exact_release",
        title="Both Sources",
        artist="Artist B",
        year=2000,
        currency="USD",
        is_active=True,
        imported_from_wantlist=True,
        imported_from_collection=True,
        created_at=now,
        updated_at=now,
    )
    collection_only = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=1003,
        discogs_master_id=5003,
        match_mode="exact_release",
        title="Collection Release",
        artist="Artist C",
        year=2001,
        currency="USD",
        is_active=True,
        imported_from_wantlist=False,
        imported_from_collection=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([want_only, both_sources, collection_only])
    db_session.flush()

    wantlist_resp = client.get(
        "/api/integrations/discogs/imported-items",
        params={"source": "wantlist", "limit": 10, "offset": 0},
        headers=h,
    )
    assert wantlist_resp.status_code == 200, wantlist_resp.text
    wantlist_body = wantlist_resp.json()
    assert wantlist_body["source"] == "wantlist"
    assert wantlist_body["count"] == 2
    want_ids = {item["discogs_release_id"] for item in wantlist_body["items"]}
    assert want_ids == {1001, 1002}

    collection_resp = client.get(
        "/api/integrations/discogs/imported-items",
        params={"source": "collection", "limit": 10, "offset": 0},
        headers=h,
    )
    assert collection_resp.status_code == 200, collection_resp.text
    collection_body = collection_resp.json()
    assert collection_body["source"] == "collection"
    assert collection_body["count"] == 2
    collection_ids = {item["discogs_release_id"] for item in collection_body["items"]}
    assert collection_ids == {1002, 1003}

    open_resp = client.get(
        f"/api/integrations/discogs/imported-items/{want_only.id}/open-in-discogs",
        params={"source": "wantlist"},
        headers=h,
    )
    assert open_resp.status_code == 200, open_resp.text
    open_body = open_resp.json()
    assert open_body["watch_release_id"] == str(want_only.id)
    assert open_body["source"] == "wantlist"
    assert open_body["open_in_discogs_url"] == "https://www.discogs.com/release/1001"

    invalid_source_open_resp = client.get(
        f"/api/integrations/discogs/imported-items/{want_only.id}/open-in-discogs",
        params={"source": "collection"},
        headers=h,
    )
    assert invalid_source_open_resp.status_code == 404, invalid_source_open_resp.text
    assert invalid_source_open_resp.json()["error"]["message"] == "Imported Discogs item not found for source"


def test_discogs_status_lazy_migrates_plaintext_token(client, user, headers, db_session):
    h = headers(user.id)
    now = datetime.now(timezone.utc)
    link = models.ExternalAccountLink(
        user_id=user.id,
        provider=models.Provider.discogs,
        external_user_id="discogs-user",
        access_token="legacy-plaintext-token",
        token_metadata={"oauth_connected": True},
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(link)
    db_session.flush()

    status = client.get("/api/integrations/discogs/status", headers=h)
    assert status.status_code == 200, status.text
    db_session.refresh(link)
    assert link.access_token is not None
    assert link.access_token.startswith("enc:v1:")
