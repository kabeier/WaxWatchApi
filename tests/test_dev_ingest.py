from __future__ import annotations

import uuid

from app.db import models


def _listing_payload(*, price: float) -> dict:
    return {
        "provider": "discogs",
        "external_id": "discogs-123",
        "url": "https://example.com/listing/123",
        "title": "Primus - Sailing the Seas of Cheese (Vinyl)",
        "price": price,
        "currency": "USD",
        "condition": "VG+",
        "seller": "seller1",
        "location": "US",
        "discogs_release_id": 123,
        "raw": {"foo": "bar"},
    }


def test_dev_ingest_creates_listing_and_snapshot(client, user, headers, db_session):
    h = headers(user.id)

    r = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0), headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["created_listing"] is True
    assert body["created_snapshot"] is True
    assert body["created_matches"] in (0, 1)

    listing_id = body["listing"]["id"]

    listing = db_session.query(models.Listing).filter(models.Listing.id == uuid.UUID(listing_id)).first()
    assert listing is not None
    snaps = db_session.query(models.PriceSnapshot).filter(models.PriceSnapshot.listing_id == listing.id).all()
    assert len(snaps) == 1


def test_dev_ingest_same_price_no_new_snapshot(client, user, headers, db_session):
    h = headers(user.id)

    r1 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0), headers=h)
    assert r1.status_code == 200, r1.text
    listing_id = uuid.UUID(r1.json()["listing"]["id"])

    r2 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0), headers=h)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["created_listing"] is False
    assert body2["created_snapshot"] is False

    snaps = db_session.query(models.PriceSnapshot).filter(models.PriceSnapshot.listing_id == listing_id).all()
    assert len(snaps) == 1


def test_dev_ingest_price_change_creates_snapshot(client, user, headers, db_session):
    h = headers(user.id)

    r1 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0), headers=h)
    assert r1.status_code == 200, r1.text
    listing_id = uuid.UUID(r1.json()["listing"]["id"])

    r2 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=45.0), headers=h)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["created_listing"] is False
    assert body2["created_snapshot"] is True

    snaps = db_session.query(models.PriceSnapshot).filter(models.PriceSnapshot.listing_id == listing_id).all()
    assert len(snaps) == 2


def test_dev_ingest_can_create_match_when_rule_exists(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Primus under $70",
        query={"keywords": ["primus", "vinyl"], "sources": ["discogs"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()

    h = headers(user.id)
    r = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0), headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["created_matches"] >= 1

    listing_id = uuid.UUID(body["listing"]["id"])
    match = (
        db_session.query(models.WatchMatch)
        .filter(models.WatchMatch.rule_id == rule.id)
        .filter(models.WatchMatch.listing_id == listing_id)
        .first()
    )
    assert match is not None


def test_dev_ingest_does_not_match_whitespace_only_keywords_rule(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Malformed keywords",
        query={"keywords": ["", "   "], "sources": ["discogs"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()

    h = headers(user.id)
    r = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0), headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["created_matches"] == 0

    listing_id = uuid.UUID(body["listing"]["id"])
    match = (
        db_session.query(models.WatchMatch)
        .filter(models.WatchMatch.rule_id == rule.id)
        .filter(models.WatchMatch.listing_id == listing_id)
        .first()
    )
    assert match is None
