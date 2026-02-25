from __future__ import annotations

from app.db import models
from app.services.ingest import ingest_and_match
from app.services.matching import ReleaseCandidate, normalize_title_tokens, score_release_candidates


def test_normalize_title_tokens_removes_noise_words_and_symbols():
    assert normalize_title_tokens("The Cure - Disintegration (LP Vinyl Remaster)") == [
        "cure",
        "disintegration",
    ]


def test_score_release_candidates_fixture_true_positive_and_false_positive_edges():
    listing_title = "Daft Punk - Discovery 2LP"
    listing_artist = "Daft Punk"

    candidates = [
        ReleaseCandidate(
            discogs_release_id=101,
            discogs_master_id=201,
            title="Discovery",
            artist="Daft Punk",
        ),
        ReleaseCandidate(
            discogs_release_id=102,
            discogs_master_id=202,
            title="Discovery Live",
            artist="Daft Funk",
        ),
        ReleaseCandidate(
            discogs_release_id=103,
            discogs_master_id=203,
            title="Homework",
            artist="Daft Punk",
        ),
    ]

    scores = score_release_candidates(
        listing_title=listing_title,
        listing_artist=listing_artist,
        candidates=candidates,
    )

    assert scores[0].candidate.discogs_release_id == 101
    assert scores[0].confidence > 0.90  # true-positive fixture

    # false-positive guard fixture: semantically-near but noisy candidate remains lower confidence
    assert scores[1].candidate.discogs_release_id == 102
    assert scores[1].confidence < scores[0].confidence


def test_ingest_enrichment_sets_discogs_mapping_when_confidence_passes_threshold(db_session, user):
    watch = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=5001,
        discogs_master_id=7001,
        match_mode="exact_release",
        title="Sailing the Seas of Cheese",
        artist="Primus",
        currency="USD",
        is_active=True,
    )
    db_session.add(watch)
    db_session.flush()

    listing_payload = {
        "provider": "ebay",
        "external_id": "ebay-map-1",
        "url": "https://www.ebay.com/itm/1",
        "title": "Primus - Sailing the Seas of Cheese LP",
        "price": 55.0,
        "currency": "USD",
        "condition": "VG+",
        "seller": "seller1",
        "location": "US",
        "raw": {"artist": "Primus"},
    }

    listing, _, _, _ = ingest_and_match(db_session, user_id=user.id, listing_payload=listing_payload)

    assert listing.discogs_release_id == 5001
    assert listing.discogs_master_id == 7001
    assert listing.raw is not None
    assert listing.raw["matching"]["discogs_mapping"]["matched"] is True
    assert listing.raw["matching"]["discogs_mapping"]["top_candidate"]["confidence"] >= 0.82


def test_ingest_enrichment_logs_below_threshold_without_mapping(db_session, user):
    watch = models.WatchRelease(
        user_id=user.id,
        discogs_release_id=8001,
        discogs_master_id=9001,
        match_mode="exact_release",
        title="Kind of Blue",
        artist="Miles Davis",
        currency="USD",
        is_active=True,
    )
    db_session.add(watch)
    db_session.flush()

    listing_payload = {
        "provider": "ebay",
        "external_id": "ebay-no-map-1",
        "url": "https://www.ebay.com/itm/2",
        "title": "Massive Attack - Mezzanine",
        "price": 40.0,
        "currency": "USD",
        "condition": "VG",
        "seller": "seller2",
        "location": "US",
        "raw": {"artist": "Massive Attack"},
    }

    listing, _, _, _ = ingest_and_match(db_session, user_id=user.id, listing_payload=listing_payload)

    assert listing.discogs_release_id is None
    assert listing.discogs_master_id is None
    assert listing.raw is not None
    assert listing.raw["matching"]["discogs_mapping"]["matched"] is False
    assert listing.raw["matching"]["discogs_mapping"]["top_candidate"]["confidence"] < 0.82
