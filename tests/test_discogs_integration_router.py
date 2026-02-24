from __future__ import annotations

from app.db import models


def test_discogs_connect_and_status(client, user, headers, db_session):
    h = headers(user.id)

    connect = client.post(
        "/api/integrations/discogs/connect",
        json={
            "external_user_id": "discogs-user",
            "access_token": "secret-token",
            "token_metadata": {"scope": "identity"},
        },
        headers=h,
    )
    assert connect.status_code == 200, connect.text
    body = connect.json()
    assert body["connected"] is True
    assert body["provider"] == "discogs"
    assert body["external_user_id"] == "discogs-user"

    status = client.get("/api/integrations/discogs/status", headers=h)
    assert status.status_code == 200, status.text
    status_body = status.json()
    assert status_body["connected"] is True
    assert status_body["has_access_token"] is True

    links = db_session.query(models.ExternalAccountLink).filter_by(user_id=user.id).all()
    assert len(links) == 1


def test_discogs_import_and_job_status(client, user, headers, db_session, monkeypatch):
    h = headers(user.id)
    client.post(
        "/api/integrations/discogs/connect",
        json={"external_user_id": "discogs-user", "access_token": "token"},
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
                                "artists": [{"name": "Artist B"}],
                            },
                        }
                    ],
                }

        return _Resp()

    monkeypatch.setattr("app.services.discogs_import.httpx.get", _fake_get)

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

    releases = db_session.query(models.WatchRelease).filter_by(user_id=user.id).all()
    assert len(releases) == 2

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
        json={"external_user_id": "discogs-user", "access_token": "token"},
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
