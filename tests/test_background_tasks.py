from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db import models
from app.db.base import SessionLocal
from app.services.background import backfill_rule_matches_task


def test_backfill_rule_matches_task_commits_rows_visible_across_sessions():
    user_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    external_id = f"background-task-{uuid.uuid4()}"

    setup_session = SessionLocal()
    try:
        user = models.User(
            id=user_id,
            email=f"background-{uuid.uuid4()}@example.com",
            hashed_password="not-a-real-hash",
            display_name="Background Task",
            is_active=True,
        )
        rule = models.WatchSearchRule(
            id=rule_id,
            user_id=user_id,
            name="Primus under $100",
            query={"keywords": ["primus", "vinyl"], "sources": ["discogs"], "max_price": 100},
            is_active=True,
            poll_interval_seconds=600,
        )
        listing = models.Listing(
            id=listing_id,
            provider=models.Provider.discogs,
            external_id=external_id,
            url=f"https://example.com/{external_id}",
            title="Primus - Sailing the Seas of Cheese (Vinyl)",
            normalized_title="primus sailing the seas of cheese vinyl",
            price=55.0,
            currency="USD",
            last_seen_at=datetime.now(timezone.utc),
            raw={"source": "test"},
        )

        setup_session.add_all([user, rule, listing])
        setup_session.commit()
    finally:
        setup_session.close()

    backfill_rule_matches_task(user_id, rule_id)

    verify_session = SessionLocal()
    try:
        match = (
            verify_session.query(models.WatchMatch)
            .filter(models.WatchMatch.rule_id == rule_id)
            .filter(models.WatchMatch.listing_id == listing_id)
            .one_or_none()
        )
        assert match is not None

        event = (
            verify_session.query(models.Event)
            .filter(models.Event.rule_id == rule_id)
            .filter(models.Event.listing_id == listing_id)
            .filter(models.Event.type == models.EventType.NEW_MATCH)
            .one_or_none()
        )
        assert event is not None
    finally:
        verify_session.close()

    cleanup_session = SessionLocal()
    try:
        cleanup_session.query(models.Listing).filter(models.Listing.id == listing_id).delete()
        cleanup_session.query(models.User).filter(models.User.id == user_id).delete()
        cleanup_session.commit()
    finally:
        cleanup_session.close()
