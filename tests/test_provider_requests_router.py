from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

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


def test_provider_requests_admin_routes_require_admin_claims(
    client, user, user2, headers, db_session, sign_jwt
):
    db_session.add_all(
        [
            models.ProviderRequest(
                user_id=user.id,
                provider=models.Provider.discogs,
                endpoint="/mine",
                method="GET",
                status_code=200,
                duration_ms=10,
                error=None,
                meta=None,
            ),
            models.ProviderRequest(
                user_id=user2.id,
                provider=models.Provider.ebay,
                endpoint="/other",
                method="GET",
                status_code=500,
                duration_ms=30,
                error="boom",
                meta=None,
            ),
        ]
    )
    db_session.flush()

    regular = headers(user.id)
    forbidden = client.get("/api/provider-requests/admin", headers=regular)
    assert forbidden.status_code == 403

    admin_token = sign_jwt(sub=str(user.id), extra_claims={"role": "admin"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    allowed = client.get("/api/provider-requests/admin", headers=admin_headers)
    assert allowed.status_code == 200, allowed.text
    payload = allowed.json()
    assert len(payload) == 2
    assert {row["user_id"] for row in payload} == {str(user.id), str(user2.id)}


def test_provider_requests_admin_filtering_and_pagination(client, user, user2, db_session, sign_jwt):
    now = datetime.now(timezone.utc)
    rows = [
        models.ProviderRequest(
            user_id=user.id,
            provider=models.Provider.discogs,
            endpoint="/discogs/200",
            method="GET",
            status_code=200,
            duration_ms=10,
            error=None,
            meta=None,
            created_at=now - timedelta(hours=2),
        ),
        models.ProviderRequest(
            user_id=user.id,
            provider=models.Provider.discogs,
            endpoint="/discogs/500",
            method="GET",
            status_code=500,
            duration_ms=15,
            error="error",
            meta=None,
            created_at=now - timedelta(minutes=30),
        ),
        models.ProviderRequest(
            user_id=user2.id,
            provider=models.Provider.ebay,
            endpoint="/ebay/404",
            method="GET",
            status_code=404,
            duration_ms=20,
            error="not found",
            meta=None,
            created_at=now - timedelta(minutes=20),
        ),
    ]
    db_session.add_all(rows)
    db_session.flush()

    admin_token = sign_jwt(sub=str(user.id), extra_claims={"app_metadata": {"roles": ["admin"]}})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    filtered = client.get(
        "/api/provider-requests/admin",
        params={
            "provider": "discogs",
            "status_code_gte": 400,
            "created_from": (now - timedelta(hours=1)).isoformat(),
            "user_id": str(user.id),
        },
        headers=admin_headers,
    )
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert len(payload) == 1
    assert payload[0]["endpoint"] == "/discogs/500"

    ordered = sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)
    first_page = client.get("/api/provider-requests/admin?limit=1", headers=admin_headers)
    assert first_page.status_code == 200
    assert first_page.json()[0]["id"] == str(ordered[0].id)

    cursor = encode_created_id_cursor(created_at=ordered[0].created_at, row_id=ordered[0].id)
    second_page = client.get(f"/api/provider-requests/admin?limit=2&cursor={cursor}", headers=admin_headers)
    assert second_page.status_code == 200
    assert [row["id"] for row in second_page.json()] == [str(ordered[1].id), str(ordered[2].id)]

    summary = client.get(
        "/api/provider-requests/admin/summary?status_code_gte=400&status_code_lte=599",
        headers=admin_headers,
    )
    assert summary.status_code == 200
    summary_payload = {row["provider"]: row for row in summary.json()}
    assert summary_payload["discogs"]["total_requests"] == 1
    assert summary_payload["ebay"]["total_requests"] == 1


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
    expected_by_id = {str(req_a.id): req_a.endpoint, str(req_b.id): req_b.endpoint}
    assert offset_resp.json()[0]["endpoint"] == expected_by_id[str(ordered[1].id)]

    cursor = encode_created_id_cursor(created_at=ordered[0].created_at, row_id=ordered[0].id)
    cursor_resp = client.get(f"/api/provider-requests?limit=5&cursor={cursor}", headers=h)
    assert cursor_resp.status_code == 200
    assert [row["endpoint"] for row in cursor_resp.json()] == [expected_by_id[str(ordered[1].id)]]


def test_provider_requests_list_returns_500_on_database_error(client, user, headers, monkeypatch):
    class _FailingPagination:
        def all(self):
            raise SQLAlchemyError("boom")

    monkeypatch.setattr(
        "app.api.routers.provider_requests.apply_created_id_pagination",
        lambda *_args, **_kwargs: _FailingPagination(),
    )

    response = client.get("/api/provider-requests", headers=headers(user.id))

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["message"] == "db error"
    assert body["error"]["code"] == "http_error"
    assert body["error"]["status"] == 500


def test_provider_requests_summary_returns_500_on_database_error(client, user, headers, monkeypatch):
    def _raise_db_error(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr("sqlalchemy.orm.Query.all", _raise_db_error)

    response = client.get("/api/provider-requests/summary", headers=headers(user.id))

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["message"] == "db error"
    assert body["error"]["code"] == "http_error"
    assert body["error"]["status"] == 500


def test_provider_requests_admin_list_returns_500_on_database_error(client, user, sign_jwt, monkeypatch):
    class _FailingPagination:
        def all(self):
            raise SQLAlchemyError("boom")

    monkeypatch.setattr(
        "app.api.routers.provider_requests.apply_created_id_pagination",
        lambda *_args, **_kwargs: _FailingPagination(),
    )

    admin_token = sign_jwt(sub=str(user.id), extra_claims={"role": "admin"})
    response = client.get(
        "/api/provider-requests/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["message"] == "db error"
    assert body["error"]["code"] == "http_error"
    assert body["error"]["status"] == 500


def test_provider_requests_admin_summary_returns_500_on_database_error(client, user, sign_jwt, monkeypatch):
    def _raise_db_error(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr("sqlalchemy.orm.Query.all", _raise_db_error)

    admin_token = sign_jwt(sub=str(user.id), extra_claims={"role": "admin"})
    response = client.get(
        "/api/provider-requests/admin/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["message"] == "db error"
    assert body["error"]["code"] == "http_error"
    assert body["error"]["status"] == 500
