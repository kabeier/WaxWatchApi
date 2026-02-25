from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.db import models
from app.tasks import backfill_rule_matches_task


def test_backfill_rule_matches_task_commits_rows_visible_across_sessions(db_session: Session, monkeypatch):
    testing_session_local = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.tasks.SessionLocal", testing_session_local)

    user_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    external_id = f"background-task-{uuid.uuid4()}"

    setup_session = testing_session_local()
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

    backfill_rule_matches_task.run(str(user_id), str(rule_id))

    verify_session = testing_session_local()
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

        notifications = (
            verify_session.query(models.Notification).filter(models.Notification.event_id == event.id).all()
        )
        assert len(notifications) == 2
        assert {notification.channel for notification in notifications} == {
            models.NotificationChannel.email,
            models.NotificationChannel.realtime,
        }
    finally:
        verify_session.close()


def test_backfill_rule_matches_task_rolls_back_when_enqueue_raises(db_session: Session, monkeypatch):
    testing_session_local = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.tasks.SessionLocal", testing_session_local)

    user_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    external_id = f"background-task-rollback-{uuid.uuid4()}"

    setup_session = testing_session_local()
    try:
        setup_session.add(
            models.User(
                id=user_id,
                email=f"background-rollback-{uuid.uuid4()}@example.com",
                hashed_password="not-a-real-hash",
                display_name="Background Task Rollback",
                is_active=True,
            )
        )
        setup_session.add(
            models.WatchSearchRule(
                id=rule_id,
                user_id=user_id,
                name="Primus under $100",
                query={"keywords": ["primus", "vinyl"], "sources": ["discogs"], "max_price": 100},
                is_active=True,
                poll_interval_seconds=600,
            )
        )
        setup_session.add(
            models.Listing(
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
        )
        setup_session.commit()
    finally:
        setup_session.close()

    def _raise_after_flush(*_args, **_kwargs):
        raise RuntimeError("forced enqueue failure")

    monkeypatch.setattr("app.services.backfill.enqueue_from_event", _raise_after_flush)

    try:
        backfill_rule_matches_task.run(str(user_id), str(rule_id))
    except RuntimeError as exc:
        assert str(exc) == "forced enqueue failure"
    else:
        raise AssertionError("Expected backfill_rule_matches_task to raise RuntimeError")

    verify_session = testing_session_local()
    try:
        assert (
            verify_session.query(models.WatchMatch)
            .filter(models.WatchMatch.rule_id == rule_id)
            .filter(models.WatchMatch.listing_id == listing_id)
            .count()
            == 0
        )
        assert (
            verify_session.query(models.Event)
            .filter(models.Event.rule_id == rule_id)
            .filter(models.Event.listing_id == listing_id)
            .count()
            == 0
        )
        assert (
            verify_session.query(models.Notification).filter(models.Notification.user_id == user_id).count()
            == 0
        )
    finally:
        verify_session.close()
