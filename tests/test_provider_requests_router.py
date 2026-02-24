from __future__ import annotations

from datetime import datetime, timezone

from app.api.pagination import encode_created_id_cursor
from app.db import models


def test_provider_requests_router_exposes_only_authenticated_user_rows(
    client, user, user2, headers, db_session
):
    own_req = models.ProviderRequest(
        user_id=user.id,
        provider=models.Provider.discogs,
        endpoint="/database/search",
        method="GET",
        status_code=200,
        duration_ms=123,
        error=None,
        meta={"rate_limit_remaining": "55"},
    )
    other_req = models.ProviderRequest(
        user_id=user2.id,
        provider=models.Provider.ebay,
        endpoint="/buy/browse/v1/item_summary/search",
        method="GET",
        status_code=429,
        duration_ms=80,
        error="rate limited",
        meta={"retry_after_seconds": 1},
    )
    db_session.add_all([own_req, other_req])
    db_session.flush()

    h = headers(user.id)

    list_resp = client.get("/api/provider-requests", headers=h)
    assert list_resp.status_code == 200, list_resp.text
    payload = list_resp.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["endpoint"] == "/database/search"
    assert payload[0]["provider"] == "discogs"

    summary_resp = client.get("/api/provider-requests/summary", headers=h)
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert len(summary) == 1
    assert summary[0]["provider"] == "discogs"
    assert summary[0]["total_requests"] == 1


def test_provider_requests_router_does_not_shadow_watch_rule_routes(client, user, headers):
    h = headers(user.id)

    resp = client.get("/api/watch-rules", headers=h)
    assert resp.status_code == 200, resp.text

    invalid = client.post("/api/provider-requests", headers=h, json={})
    assert invalid.status_code == 405


def test_provider_requests_pagination_stable_ordering_under_ties(client, user, headers, db_session):
    shared_ts = datetime.now(timezone.utc)
    req_a = models.ProviderRequest(
        user_id=user.id,
        provider=models.Provider.discogs,
        endpoint="/a",
        method="GET",
        status_code=200,
        duration_ms=10,
        error=None,
        meta=None,
        created_at=shared_ts,
    )
    req_b = models.ProviderRequest(
        user_id=user.id,
        provider=models.Provider.discogs,
        endpoint="/b",
        method="GET",
        status_code=200,
        duration_ms=20,
        error=None,
        meta=None,
        created_at=shared_ts,
    )
    db_session.add_all([req_a, req_b])
    db_session.flush()

    ordered = sorted([req_a, req_b], key=lambda r: r.id, reverse=True)
    h = headers(user.id)

    offset_resp = client.get("/api/provider-requests?limit=1&offset=1", headers=h)
    assert offset_resp.status_code == 200
    assert offset_resp.json()[0]["id"] == str(ordered[1].id)

    cursor = encode_created_id_cursor(created_at=ordered[0].created_at, row_id=ordered[0].id)
    cursor_resp = client.get(f"/api/provider-requests?limit=5&cursor={cursor}", headers=h)
    assert cursor_resp.status_code == 200
    assert [row["id"] for row in cursor_resp.json()] == [str(ordered[1].id)]
