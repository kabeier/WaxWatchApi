from __future__ import annotations

from app.db import models


def test_dev_run_rule_returns_summary_shape(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Primus under $70",
        query={"keywords": ["primus"], "sources": ["discogs"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()

    h = headers(user.id)
    r = client.post(f"/api/dev/rules/{rule.id}/run?limit=5", headers=h)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["rule_id"] == str(rule.id)
    assert isinstance(body["fetched"], int)
    assert isinstance(body["listings_created"], int)
    assert isinstance(body["snapshots_created"], int)
    assert isinstance(body["matches_created"], int)


def test_dev_run_rule_not_found(client, user, headers):
    h = headers(user.id)
    missing = "00000000-0000-0000-0000-000000000000"

    r = client.post(f"/api/dev/rules/{missing}/run?limit=5", headers=h)
    assert r.status_code == 404, r.text


def test_dev_run_rule_with_mock_source_ingests_rows(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Mock source",
        query={"keywords": ["primus", "vinyl"], "sources": ["mock"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()

    h = headers(user.id)
    r = client.post(f"/api/dev/rules/{rule.id}/run?limit=5", headers=h)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["fetched"] >= 1
    assert body["listings_created"] >= 1

    listings = db_session.query(models.Listing).all()
    assert len(listings) >= 1

    req = db_session.query(models.ProviderRequest).order_by(models.ProviderRequest.created_at.desc()).first()
    assert req is not None
    assert req.provider.value == "mock"
