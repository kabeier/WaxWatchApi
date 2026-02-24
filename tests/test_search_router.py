from __future__ import annotations

from app.db import models


def test_search_endpoint_returns_paginated_results_and_logs_requests(client, user, headers, db_session):
    resp = client.post(
        "/api/search",
        headers=headers(user.id),
        json={
            "keywords": ["primus", "vinyl"],
            "providers": ["mock", "discogs"],
            "page": 1,
            "page_size": 3,
            "min_price": 0,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == 3
    assert body["pagination"]["returned"] <= 3
    assert set(body["providers_searched"]) == {"mock", "discogs"}
    assert isinstance(body["items"], list)

    logged = db_session.query(models.ProviderRequest).all()
    assert len(logged) == 2
    assert {row.provider.value for row in logged} == {"mock", "discogs"}
    assert all(row.status_code == 200 for row in logged)


def test_search_save_alert_creates_watch_rule(client, user, headers, db_session):
    resp = client.post(
        "/api/search/save-alert",
        headers=headers(user.id),
        json={
            "name": "Cheap Primus Vinyl",
            "poll_interval_seconds": 900,
            "query": {
                "keywords": ["primus", "vinyl"],
                "providers": ["mock"],
                "max_price": 55,
                "min_condition": "VG",
            },
        },
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["name"] == "Cheap Primus Vinyl"
    assert payload["query"]["sources"] == ["mock"]
    assert payload["query"]["max_price"] == 55
    assert payload["poll_interval_seconds"] == 900

    rule = db_session.query(models.WatchSearchRule).filter_by(id=payload["id"]).first()
    assert rule is not None
    assert rule.query["sources"] == ["mock"]


def test_search_rejects_unsupported_provider(client, user, headers):
    resp = client.post(
        "/api/search",
        headers=headers(user.id),
        json={
            "keywords": ["primus"],
            "providers": ["spotify"],
        },
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
