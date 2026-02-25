from __future__ import annotations

from app.db import models


def test_outbound_ebay_redirect_logs_click_and_redirects(client, user, headers, db_session, monkeypatch):
    monkeypatch.setattr("app.monetization.ebay_affiliate.settings.ebay_campaign_id", "12345")
    monkeypatch.setattr("app.monetization.ebay_affiliate.settings.ebay_custom_id", "waxwatch")

    listing = models.Listing(
        provider=models.Provider.ebay,
        external_id="ebay-123",
        url="https://www.ebay.com/itm/123",
        title="Primus record",
        normalized_title="primus record",
        price=42.0,
        currency="USD",
        status=models.ListingStatus.active,
    )
    db_session.add(listing)
    db_session.flush()

    response = client.get(
        f"/api/outbound/ebay/{listing.id}",
        headers={**headers(user.id), "Referer": "https://app.example.com/search"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://www.ebay.com/itm/123")
    assert "campid=12345" in location
    assert "customid=waxwatch" in location

    click = db_session.query(models.OutboundClick).one()
    assert click.user_id == user.id
    assert click.listing_id == listing.id
    assert click.provider == models.Provider.ebay
    assert click.referrer == "https://app.example.com/search"


def test_outbound_ebay_redirect_404_for_non_ebay_listing(client, user, headers, db_session):
    listing = models.Listing(
        provider=models.Provider.discogs,
        external_id="discogs-123",
        url="https://www.discogs.com/sell/item/123",
        title="Primus record",
        normalized_title="primus record",
        price=42.0,
        currency="USD",
        status=models.ListingStatus.active,
    )
    db_session.add(listing)
    db_session.flush()

    response = client.get(
        f"/api/outbound/ebay/{listing.id}", headers=headers(user.id), follow_redirects=False
    )

    assert response.status_code == 404
    assert db_session.query(models.OutboundClick).count() == 0


def test_outbound_ebay_redirect_404_for_missing_listing(client, user, headers, db_session):
    response = client.get(
        "/api/outbound/ebay/00000000-0000-0000-0000-000000000000",
        headers=headers(user.id),
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert db_session.query(models.OutboundClick).count() == 0


def test_outbound_ebay_redirect_404_for_unavailable_destination(client, user, headers, db_session):
    listing = models.Listing(
        provider=models.Provider.ebay,
        external_id="ebay-456",
        url="   ",
        title="Unavailable record",
        normalized_title="unavailable record",
        price=13.0,
        currency="USD",
        status=models.ListingStatus.active,
    )
    db_session.add(listing)
    db_session.flush()

    response = client.get(f"/api/outbound/ebay/{listing.id}", headers=headers(user.id), follow_redirects=False)

    assert response.status_code == 404
    assert db_session.query(models.OutboundClick).count() == 0
