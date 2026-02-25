from __future__ import annotations

import uuid

from app.db import models
from app.services.backfill import _rule_matches_listing as backfill_rule_matches_listing
from app.services.ingest import _rule_matches_listing as ingest_rule_matches_listing
from app.services.ingest import normalize_title


def test_rule_matching_rejects_whitespace_only_keywords_for_ingest_and_backfill():
    rule = models.WatchSearchRule(
        user_id=uuid.uuid4(),
        name="Whitespace keywords",
        query={"keywords": ["", "   "], "sources": ["discogs"]},
        is_active=True,
        poll_interval_seconds=600,
    )
    listing = models.Listing(
        provider=models.Provider.discogs,
        external_id="discogs-1",
        url="https://example.com/listing/1",
        title="Primus - Sailing the Seas of Cheese (Vinyl)",
        normalized_title=normalize_title("Primus - Sailing the Seas of Cheese (Vinyl)"),
        price=50,
        currency="USD",
        status=models.ListingStatus.active,
    )

    assert ingest_rule_matches_listing(rule, listing, listing.normalized_title or "") is False
    assert backfill_rule_matches_listing(rule, listing, listing.normalized_title or "") is False


def test_rule_matching_rejects_mixed_currency_max_price_for_ingest_and_backfill():
    rule = models.WatchSearchRule(
        user_id=uuid.uuid4(),
        name="USD price cap",
        query={"keywords": ["primus"], "sources": ["discogs"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    listing = models.Listing(
        provider=models.Provider.discogs,
        external_id="discogs-2",
        url="https://example.com/listing/2",
        title="Primus - Sailing the Seas of Cheese (Vinyl)",
        normalized_title=normalize_title("Primus - Sailing the Seas of Cheese (Vinyl)"),
        price=50,
        currency="EUR",
        status=models.ListingStatus.active,
    )

    assert (
        ingest_rule_matches_listing(
            rule,
            listing,
            listing.normalized_title or "",
            user_currency="USD",
        )
        is False
    )
    assert (
        backfill_rule_matches_listing(
            rule,
            listing,
            listing.normalized_title or "",
            user_currency="USD",
        )
        is False
    )


def test_rule_matching_allows_explicit_query_currency_for_ingest_and_backfill():
    rule = models.WatchSearchRule(
        user_id=uuid.uuid4(),
        name="EUR price cap",
        query={"keywords": ["primus"], "sources": ["discogs"], "max_price": 70, "currency": "EUR"},
        is_active=True,
        poll_interval_seconds=600,
    )
    listing = models.Listing(
        provider=models.Provider.discogs,
        external_id="discogs-3",
        url="https://example.com/listing/3",
        title="Primus - Sailing the Seas of Cheese (Vinyl)",
        normalized_title=normalize_title("Primus - Sailing the Seas of Cheese (Vinyl)"),
        price=50,
        currency="EUR",
        status=models.ListingStatus.active,
    )

    assert ingest_rule_matches_listing(rule, listing, listing.normalized_title or "") is True
    assert backfill_rule_matches_listing(rule, listing, listing.normalized_title or "") is True
