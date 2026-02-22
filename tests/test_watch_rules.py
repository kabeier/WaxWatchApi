from __future__ import annotations

import uuid


def _headers(user_id: uuid.UUID | None = None) -> dict[str, str]:
    return {"X-User-Id": str(user_id or uuid.uuid4())}


def test_create_and_list_watch_rules(client, user):
    headers = _headers(user.id)

    payload = {
        "name": "Primus under $70",
        "query": {"keywords": ["primus"], "sources": ["discogs"], "max_price": 70},
        "poll_interval_seconds": 600,
    }

    r = client.post("/api/watch-rules", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "Primus under $70"
    assert created["query"]["max_price"] == 70

    r2 = client.get("/api/watch-rules?limit=50&offset=0", headers=headers)
    assert r2.status_code == 200
    rows = r2.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1
