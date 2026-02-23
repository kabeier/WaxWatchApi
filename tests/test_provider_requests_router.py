from __future__ import annotations

from app.db import models


def test_provider_requests_router_exposes_read_only_endpoints(client, user, headers, db_session):
    req = models.ProviderRequest(
        provider=models.Provider.discogs,
        endpoint="/database/search",
        method="GET",
        status_code=200,
        duration_ms=123,
        error=None,
        meta={"rate_limit_remaining": "55"},
    )
    db_session.add(req)
    db_session.flush()

    h = headers(user.id)

    list_resp = client.get("/api/provider-requests", headers=h)
    assert list_resp.status_code == 200, list_resp.text
    assert isinstance(list_resp.json(), list)
    assert list_resp.json()[0]["endpoint"] == "/database/search"

    summary_resp = client.get("/api/provider-requests/summary", headers=h)
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert summary[0]["provider"] == "discogs"


def test_provider_requests_router_does_not_shadow_watch_rule_routes(client, user, headers):
    h = headers(user.id)

    resp = client.get("/api/watch-rules", headers=h)
    assert resp.status_code == 200, resp.text

    invalid = client.post("/api/provider-requests", headers=h, json={})
    assert invalid.status_code == 405
