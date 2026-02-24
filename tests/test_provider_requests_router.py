from __future__ import annotations

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
