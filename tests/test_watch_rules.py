from __future__ import annotations

import uuid
from datetime import datetime

from app.api.pagination import encode_created_id_cursor
from app.db import models


def _create_rule(client, headers: dict[str, str], *, name: str = "Primus under $70", query=None, poll=600):
    if query is None:
        query = {"keywords": ["primus"], "sources": ["discogs"], "max_price": 70}

    payload = {
        "name": name,
        "query": query,
        "poll_interval_seconds": poll,
    }
    r = client.post("/api/watch-rules", json=payload, headers=headers)
    return r


def test_create_rule_success(client, user, headers):
    h = headers(user.id)

    r = _create_rule(client, h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Primus under $70"
    assert body["user_id"] == str(user.id)
    assert body["query"]["max_price"] == 70
    assert body["query"]["sources"] == ["discogs"]


def test_list_rules_pagination(client, user, headers):
    h = headers(user.id)

    for i in range(3):
        r = _create_rule(client, h, name=f"Rule {i + 1}")
        assert r.status_code == 201, r.text

    r1 = client.get("/api/watch-rules?limit=2&offset=0", headers=h)
    assert r1.status_code == 200, r1.text
    rows1 = r1.json()
    assert len(rows1) == 2

    r2 = client.get("/api/watch-rules?limit=2&offset=2", headers=h)
    assert r2.status_code == 200, r2.text
    rows2 = r2.json()
    assert len(rows2) == 1


def test_get_rule_success(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    r = client.get(f"/api/watch-rules/{rule_id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == rule_id
    assert body["user_id"] == str(user.id)


def test_get_rule_not_found(client, user, headers):
    h = headers(user.id)
    missing = uuid.uuid4()

    r = client.get(f"/api/watch-rules/{missing}", headers=h)
    assert r.status_code == 404, r.text


def test_get_rule_cross_user_isolation(client, user, user2, headers):
    h1 = headers(user.id)
    h2 = headers(user2.id)

    created = _create_rule(client, h1)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    r = client.get(f"/api/watch-rules/{rule_id}", headers=h2)
    assert r.status_code == 404, r.text


def test_patch_rule_updates_fields(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    patch_payload = {
        "name": "Primus under $55",
        "query": {"keywords": ["primus", "vinyl"], "sources": ["discogs"], "max_price": 55},
        "is_active": True,
        "poll_interval_seconds": 900,
    }

    r = client.patch(f"/api/watch-rules/{rule_id}", json=patch_payload, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Primus under $55"
    assert body["query"]["max_price"] == 55
    assert body["query"]["keywords"] == ["primus", "vinyl"]
    assert body["poll_interval_seconds"] == 900


def test_patch_rule_not_found(client, user, headers):
    h = headers(user.id)
    missing = uuid.uuid4()

    r = client.patch(f"/api/watch-rules/{missing}", json={"name": "Nope"}, headers=h)
    assert r.status_code == 404, r.text


def test_patch_rule_validation_invalid_provider(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    rule_id = created.json()["id"]

    r = client.patch(
        f"/api/watch-rules/{rule_id}",
        json={"query": {"sources": ["not-a-real-provider"]}},
        headers=h,
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["status"] == 422
    assert isinstance(body["error"]["details"], list)
    assert "not-a-real-provider" in str(body["error"]["details"])


def test_delete_rule_disables(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    r = client.delete(f"/api/watch-rules/{rule_id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_active"] is False

    r2 = client.get(f"/api/watch-rules/{rule_id}", headers=h)
    assert r2.status_code == 200, r2.text
    assert r2.json()["is_active"] is False


def test_delete_rule_cross_user_isolation(client, user, user2, headers):
    h1 = headers(user.id)
    h2 = headers(user2.id)

    created = _create_rule(client, h1)
    rule_id = created.json()["id"]

    r = client.delete(f"/api/watch-rules/{rule_id}", headers=h2)
    assert r.status_code == 404, r.text


def test_create_rule_requires_sources_on_create(client, user, headers):
    h = headers(user.id)

    payload = {
        "name": "Missing sources",
        "query": {"keywords": ["primus"], "max_price": 70},
        "poll_interval_seconds": 600,
    }
    r = client.post("/api/watch-rules", json=payload, headers=h)
    assert r.status_code == 422, r.text


def test_create_rule_rejects_empty_sources(client, user, headers):
    h = headers(user.id)

    payload = {
        "name": "Empty sources",
        "query": {"keywords": ["primus"], "sources": [], "max_price": 70},
        "poll_interval_seconds": 600,
    }
    r = client.post("/api/watch-rules", json=payload, headers=h)
    assert r.status_code == 422, r.text


def test_create_rule_poll_interval_bounds(client, user, headers):
    h = headers(user.id)

    # too low (min is 30)
    payload_low = {
        "name": "Bad poll low",
        "query": {"keywords": ["primus"], "sources": ["discogs"], "max_price": 70},
        "poll_interval_seconds": 1,
    }
    r1 = client.post("/api/watch-rules", json=payload_low, headers=h)
    assert r1.status_code == 422, r1.text

    # too high (max is 86400)
    payload_high = {
        "name": "Bad poll high",
        "query": {"keywords": ["primus"], "sources": ["discogs"], "max_price": 70},
        "poll_interval_seconds": 999999,
    }
    r2 = client.post("/api/watch-rules", json=payload_high, headers=h)
    assert r2.status_code == 422, r2.text


def test_disable_endpoint_and_hard_delete(client, user, headers, db_session):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    disabled = client.post(f"/api/watch-rules/{rule_id}/disable", headers=h)
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["is_active"] is False

    hard_deleted = client.delete(f"/api/watch-rules/{rule_id}/hard", headers=h)
    assert hard_deleted.status_code == 204, hard_deleted.text

    fetched = client.get(f"/api/watch-rules/{rule_id}", headers=h)
    assert fetched.status_code == 404, fetched.text

    event_types = [
        e.type for e in db_session.query(models.Event).filter(models.Event.user_id == user.id).all()
    ]
    assert models.EventType.RULE_DISABLED in event_types
    assert models.EventType.RULE_DELETED in event_types


def test_create_rule_rejects_whitespace_only_keywords(client, user, headers):
    h = headers(user.id)

    payload = {
        "name": "Bad keywords",
        "query": {"keywords": ["", "   "], "sources": ["discogs"], "max_price": 70},
        "poll_interval_seconds": 600,
    }
    r = client.post("/api/watch-rules", json=payload, headers=h)
    assert r.status_code == 422, r.text


def test_patch_rule_rejects_whitespace_only_keywords(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    r = client.patch(
        f"/api/watch-rules/{rule_id}",
        json={"query": {"keywords": ["", "   "]}},
        headers=h,
    )
    assert r.status_code == 422, r.text


def test_create_rule_rejects_negative_max_price(client, user, headers):
    h = headers(user.id)

    payload = {
        "name": "Negative max price",
        "query": {"keywords": ["primus"], "sources": ["discogs"], "max_price": -1},
        "poll_interval_seconds": 600,
    }
    r = client.post("/api/watch-rules", json=payload, headers=h)
    assert r.status_code == 422, r.text


def test_create_rule_rejects_non_numeric_max_price(client, user, headers):
    h = headers(user.id)

    payload = {
        "name": "Non numeric max price",
        "query": {"keywords": ["primus"], "sources": ["discogs"], "max_price": "cheap"},
        "poll_interval_seconds": 600,
    }
    r = client.post("/api/watch-rules", json=payload, headers=h)
    assert r.status_code == 422, r.text


def test_patch_rule_rejects_non_numeric_max_price(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    r = client.patch(
        f"/api/watch-rules/{rule_id}",
        json={"query": {"max_price": "not-a-number"}},
        headers=h,
    )
    assert r.status_code == 422, r.text


def test_create_rule_rejects_malformed_query_payload(client, user, headers):
    h = headers(user.id)

    payload = {
        "name": "Malformed query",
        "query": ["not", "an", "object"],
        "poll_interval_seconds": 600,
    }
    r = client.post("/api/watch-rules", json=payload, headers=h)
    assert r.status_code == 422, r.text


def test_patch_rule_rejects_malformed_query_payload(client, user, headers):
    h = headers(user.id)

    created = _create_rule(client, h)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    r = client.patch(
        f"/api/watch-rules/{rule_id}",
        json={"query": "not-an-object"},
        headers=h,
    )
    assert r.status_code == 422, r.text


def test_watch_rules_cursor_pagination(client, user, headers):
    h = headers(user.id)
    first = _create_rule(client, h, name="A")
    second = _create_rule(client, h, name="B")
    assert first.status_code == 201 and second.status_code == 201

    rows = client.get("/api/watch-rules?limit=2", headers=h).json()
    cursor = encode_created_id_cursor(
        created_at=datetime.fromisoformat(rows[0]["created_at"]),
        row_id=uuid.UUID(rows[0]["id"]),
    )

    resp = client.get(f"/api/watch-rules?limit=2&cursor={cursor}", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
