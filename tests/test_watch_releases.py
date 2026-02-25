from __future__ import annotations

import uuid


def _create_watch_release(client, headers: dict[str, str], *, title: str = "Rust in Peace"):
    payload = {
        "discogs_release_id": 12345,
        "discogs_master_id": 4444,
        "match_mode": "exact_release",
        "title": title,
        "artist": "Megadeth",
        "year": 1990,
        "target_price": 45.5,
        "currency": "usd",
        "min_condition": "VG+",
        "is_active": True,
    }
    return client.post("/api/watch-releases", json=payload, headers=headers)


def test_watch_release_crud_and_soft_delete(client, user, headers):
    h = headers(user.id)

    created = _create_watch_release(client, h)
    assert created.status_code == 201, created.text
    created_body = created.json()
    watch_release_id = created_body["id"]
    assert created_body["currency"] == "USD"
    assert created_body["discogs_master_id"] == 4444
    assert created_body["match_mode"] == "exact_release"

    listed = client.get("/api/watch-releases", headers=h)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1

    fetched = client.get(f"/api/watch-releases/{watch_release_id}", headers=h)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["title"] == "Rust in Peace"

    patched = client.patch(
        f"/api/watch-releases/{watch_release_id}",
        json={
            "title": "Peace Sells",
            "currency": "eur",
            "target_price": 40.0,
            "match_mode": "master_release",
        },
        headers=h,
    )
    assert patched.status_code == 200, patched.text
    patched_body = patched.json()
    assert patched_body["title"] == "Peace Sells"
    assert patched_body["currency"] == "EUR"
    assert patched_body["target_price"] == 40.0
    assert patched_body["match_mode"] == "master_release"

    deleted = client.delete(f"/api/watch-releases/{watch_release_id}", headers=h)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["is_active"] is False


def test_watch_release_get_cross_user_isolation(client, user, user2, headers):
    h1 = headers(user.id)
    h2 = headers(user2.id)

    created = _create_watch_release(client, h1)
    watch_release_id = created.json()["id"]

    r = client.get(f"/api/watch-releases/{watch_release_id}", headers=h2)
    assert r.status_code == 404, r.text


def test_watch_release_not_found(client, user, headers):
    h = headers(user.id)
    missing = uuid.uuid4()

    r = client.patch(f"/api/watch-releases/{missing}", json={"title": "Nope"}, headers=h)
    assert r.status_code == 404, r.text


def test_watch_release_master_mode_requires_master_id(client, user, headers):
    h = headers(user.id)

    create_resp = client.post(
        "/api/watch-releases",
        json={
            "discogs_release_id": 12345,
            "match_mode": "master_release",
            "title": "Rust in Peace",
            "currency": "USD",
            "is_active": True,
        },
        headers=h,
    )
    assert create_resp.status_code == 422, create_resp.text


def test_watch_release_update_master_mode_requires_master_id(client, user, headers):
    h = headers(user.id)
    created = _create_watch_release(client, h)
    watch_release_id = created.json()["id"]

    update_resp = client.patch(
        f"/api/watch-releases/{watch_release_id}",
        json={"match_mode": "master_release", "discogs_master_id": None},
        headers=h,
    )
    assert update_resp.status_code == 422, update_resp.text
