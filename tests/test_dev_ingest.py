from __future__ import annotations

import uuid

from app.db import models


def _listing_payload(
    *,
    price: float,
    release_id: int = 123,
    master_id: int | None = None,
    provider: str = "discogs",
    external_id: str = "discogs-123",
    url: str = "https://example.com/listing/123",
    currency: str = "USD",
) -> dict:
    return {
        "provider": provider,
        "external_id": external_id,
        "url": url,
        "title": "Primus - Sailing the Seas of Cheese (Vinyl)",
        "price": price,
        "currency": currency,
        "condition": "VG+",
        "seller": "seller1",
        "location": "US",
        "discogs_release_id": release_id,
        "discogs_master_id": master_id,
        "raw": {"foo": "bar"},
    }


def test_dev_ingest_exposes_tracked_public_url_for_ebay(client, user, headers):
    h = headers(user.id)

    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(
            price=50.0,
            provider="ebay",
            external_id="ebay-123",
            url="https://www.ebay.com/itm/123",
        ),
        headers=h,
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["listing"]["public_url"] == f"/api/outbound/ebay/{body['listing']['id']}"


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


def test_dev_ingest_same_price_and_currency_no_new_snapshot(client, user, headers, db_session):
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


def test_dev_ingest_same_price_changed_currency_creates_snapshot(client, user, headers, db_session):
    h = headers(user.id)

    r1 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0, currency="USD"), headers=h)
    assert r1.status_code == 200, r1.text
    listing_id = uuid.UUID(r1.json()["listing"]["id"])

    r2 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0, currency="EUR"), headers=h)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["created_listing"] is False
    assert body2["created_snapshot"] is True

    snaps = db_session.query(models.PriceSnapshot).filter(models.PriceSnapshot.listing_id == listing_id).all()
    assert len(snaps) == 2


def test_dev_ingest_price_and_currency_change_creates_snapshot(client, user, headers, db_session):
    h = headers(user.id)

    r1 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=50.0, currency="USD"), headers=h)
    assert r1.status_code == 200, r1.text
    listing_id = uuid.UUID(r1.json()["listing"]["id"])

    r2 = client.post("/api/dev/listings/ingest", json=_listing_payload(price=45.0, currency="EUR"), headers=h)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["created_listing"] is False
    assert body2["created_snapshot"] is True

    snaps = db_session.query(models.PriceSnapshot).filter(models.PriceSnapshot.listing_id == listing_id).all()
    assert len(snaps) == 2


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


def test_dev_ingest_price_rule_skips_non_comparable_currency(client, user, headers, db_session):
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
    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(price=50.0, currency="EUR"),
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["created_matches"] == 0


def test_dev_ingest_price_rule_uses_explicit_query_currency(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Primus under €70",
        query={
            "keywords": ["primus", "vinyl"],
            "sources": ["discogs"],
            "max_price": 70,
            "currency": "EUR",
        },
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()

    h = headers(user.id)
    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(price=50.0, currency="EUR"),
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["created_matches"] >= 1


def test_dev_ingest_match_event_uses_tracked_url_for_ebay(client, user, headers, db_session):
    rule = models.WatchSearchRule(
        user_id=user.id,
        name="Primus under $70",
        query={"keywords": ["primus", "vinyl"], "sources": ["ebay"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()

    h = headers(user.id)
    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(
            price=50.0,
            provider="ebay",
            external_id="ebay-777",
            url="https://www.ebay.com/itm/777",
        ),
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    listing_id = body["listing"]["id"]
    event = (
        db_session.query(models.Event)
        .filter(models.Event.rule_id == rule.id)
        .filter(models.Event.listing_id == listing_id)
        .one()
    )
    assert event.payload is not None
    assert event.payload["url"] == f"/api/outbound/ebay/{listing_id}"


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


def test_dev_ingest_matches_exact_release_mode_only_on_release_id(client, user, headers, db_session):
    watch = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=123,
        discogs_master_id=9999,
        match_mode="exact_release",
        title="Exact Watch",
        currency="USD",
        is_active=True,
    )
    db_session.add(watch)
    db_session.flush()

    h = headers(user.id)
    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(price=50.0, release_id=123, master_id=8888),
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_matches"] == 1

    listing_id = uuid.UUID(r.json()["listing"]["id"])
    release_events = (
        db_session.query(models.Event)
        .filter(models.Event.watch_release_id == watch.id)
        .filter(models.Event.listing_id == listing_id)
        .all()
    )
    assert len(release_events) == 1


def test_dev_ingest_matches_master_release_mode_only_on_master_id(client, user, headers, db_session):
    watch = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=123,
        discogs_master_id=555,
        match_mode="master_release",
        title="Master Watch",
        currency="USD",
        is_active=True,
    )
    db_session.add(watch)
    db_session.flush()

    h = headers(user.id)
    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(price=50.0, release_id=789, master_id=555),
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_matches"] == 1


def test_dev_ingest_watch_release_mode_false_positive_controls(client, user, headers, db_session):
    exact_watch = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=123,
        discogs_master_id=555,
        match_mode="exact_release",
        title="Exact Watch",
        currency="USD",
        is_active=True,
    )
    master_watch = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=456,
        discogs_master_id=777,
        match_mode="master_release",
        title="Master Watch",
        currency="USD",
        is_active=True,
    )
    db_session.add_all([exact_watch, master_watch])
    db_session.flush()

    h = headers(user.id)
    r = client.post(
        "/api/dev/listings/ingest",
        json=_listing_payload(price=50.0, release_id=999, master_id=111),
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_matches"] == 0

    listing_id = uuid.UUID(r.json()["listing"]["id"])
    release_events = (
        db_session.query(models.Event)
        .filter(models.Event.listing_id == listing_id)
        .filter(models.Event.watch_release_id.is_not(None))
        .all()
    )
    assert not release_events
