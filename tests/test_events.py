from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import models


def test_list_events_filters_by_user_and_orders_desc(client, user, user2, headers, db_session):
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
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
