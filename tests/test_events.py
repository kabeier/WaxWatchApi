from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.pagination import encode_created_id_cursor
from app.db import models


def test_list_events_filters_by_user_and_orders_desc(client, user, user2, headers, db_session):
    now = datetime.now(timezone.utc)
    e1 = models.Event(
        user_id=user.id,
        type=models.EventType.RULE_CREATED,
        payload={"n": 1},
        created_at=now - timedelta(minutes=10),
    )
    e2 = models.Event(
        user_id=user.id,
        type=models.EventType.NEW_MATCH,
        payload={"n": 2},
        created_at=now - timedelta(minutes=5),
    )
    e3 = models.Event(
        user_id=user.id,
        type=models.EventType.RULE_UPDATED,
        payload={"n": 3},
        created_at=now - timedelta(minutes=1),
    )

    # should not appear
    other = models.Event(
        user_id=user2.id,
        type=models.EventType.RULE_CREATED,
        payload={"other": True},
        created_at=now,
    )

    db_session.add_all([e1, e2, e3, other])
    db_session.flush()

    h = headers(user.id)
    r = client.get("/api/events?limit=50", headers=h)
    assert r.status_code == 200, r.text

    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) == 3

    # ordering
    assert rows[0]["type"] == models.EventType.RULE_UPDATED.value
    assert rows[1]["type"] == models.EventType.NEW_MATCH.value
    assert rows[2]["type"] == models.EventType.RULE_CREATED.value


def test_list_events_limit(client, user, headers, db_session):
    now = datetime.now(timezone.utc)
    for i in range(5):
        db_session.add(
            models.Event(
                user_id=user.id,
                type=models.EventType.RULE_CREATED,
                payload={"i": i},
                created_at=now - timedelta(seconds=i),
            )
        )
    db_session.flush()

    h = headers(user.id)
    r = client.get("/api/events?limit=2", headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 2


def test_list_events_offset_and_empty_page(client, user, headers, db_session):
    now = datetime.now(timezone.utc)
    for i in range(3):
        db_session.add(
            models.Event(
                user_id=user.id,
                type=models.EventType.RULE_CREATED,
                payload={"i": i},
                created_at=now - timedelta(seconds=i),
            )
        )
    db_session.flush()

    h = headers(user.id)
    offset_resp = client.get("/api/events?limit=2&offset=1", headers=h)
    assert offset_resp.status_code == 200, offset_resp.text
    assert len(offset_resp.json()) == 2

    empty_resp = client.get("/api/events?limit=2&offset=10", headers=h)
    assert empty_resp.status_code == 200, empty_resp.text
    assert empty_resp.json() == []


def test_list_events_cursor_with_tie_breaker_and_invalid_mix(client, user, headers, db_session):
    shared_ts = datetime.now(timezone.utc)
    events: list[models.Event] = []
    for event_type in [
        models.EventType.RULE_CREATED,
        models.EventType.RULE_UPDATED,
        models.EventType.NEW_MATCH,
    ]:
        event = models.Event(user_id=user.id, type=event_type, payload=None, created_at=shared_ts)
        db_session.add(event)
        events.append(event)
    db_session.flush()

    ordered = sorted(events, key=lambda e: e.id, reverse=True)
    cursor = encode_created_id_cursor(created_at=ordered[0].created_at, row_id=ordered[0].id)

    h = headers(user.id)
    cursor_resp = client.get(f"/api/events?limit=5&cursor={cursor}", headers=h)
    assert cursor_resp.status_code == 200, cursor_resp.text
    payload = cursor_resp.json()
    assert [row["id"] for row in payload] == [str(ordered[1].id), str(ordered[2].id)]

    invalid_mix = client.get(f"/api/events?limit=5&offset=1&cursor={cursor}", headers=h)
    assert invalid_mix.status_code == 422
