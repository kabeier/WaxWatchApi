from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db import models
from app.services.ingest import normalize_title
from app.services.notifications import enqueue_from_event

logger = get_logger(__name__)


def _rule_matches_listing(
    rule: models.WatchSearchRule, listing: models.Listing, normalized_title: str
) -> bool:
    q: dict[str, Any] = rule.query or {}

    sources = q.get("sources")
    if isinstance(sources, list) and sources:
        allowed = [str(s).strip().lower() for s in sources if str(s).strip()]
        if listing.provider.value not in allowed:
            return False

    max_price = q.get("max_price")
    if isinstance(max_price, (int | float)):
        if float(listing.price) > float(max_price):
            return False

    keywords = q.get("keywords")
    if isinstance(keywords, list) and keywords:
        kws = [str(k).strip().lower() for k in keywords if str(k).strip()]
        for kw in kws:
            if kw not in normalized_title:
                return False

    return True


def backfill_matches_for_rule(
    db: Session,
    *,
    user_id: UUID,
    rule_id: UUID,
    days: int | None = None,
    limit: int | None = None,
) -> int:
    """
    Backfill matches for an active rule by scanning recent listings.
    """
    if not settings.dev_backfill_on_rule_change:
        return 0

    days = days if days is not None else settings.dev_backfill_days
    limit = limit if limit is not None else settings.dev_backfill_limit

    rule = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.id == rule_id)
        .filter(models.WatchSearchRule.user_id == user_id)
        .first()
    )
    if not rule or not rule.is_active:
        return 0

    since = datetime.now(timezone.utc) - timedelta(days=days)

    listings = (
        db.query(models.Listing)
        .filter(models.Listing.last_seen_at >= since)
        .order_by(models.Listing.last_seen_at.desc())
        .limit(limit)
        .all()
    )

    created = 0
    now = datetime.now(timezone.utc)

    for listing in listings:
        title_norm = listing.normalized_title or normalize_title(listing.title)

        if not _rule_matches_listing(rule, listing, title_norm):
            continue

        # still subject to race
        exists = (
            db.query(models.WatchMatch)
            .filter(models.WatchMatch.rule_id == rule.id)
            .filter(models.WatchMatch.listing_id == listing.id)
            .first()
        )
        if exists:
            continue

        match = models.WatchMatch(
            rule_id=rule.id,
            listing_id=listing.id,
            matched_at=now,
            match_context={"reason": "backfill_recent_listings", "days": days},
        )
        ev = models.Event(
            user_id=user_id,
            type=models.EventType.NEW_MATCH,
            rule_id=rule.id,
            listing_id=listing.id,
            payload={
                "rule_name": rule.name,
                "listing_title": listing.title,
                "price": float(listing.price),
                "currency": listing.currency,
                "provider": listing.provider.value,
                "url": listing.url,
                "backfill": True,
                "days": days,
            },
            created_at=now,
        )

        db.add(match)
        db.add(ev)

        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            continue

        enqueue_from_event(db, event=ev)
        created += 1

    if created:
        db.flush()

    logger.info(
        "backfill.completed",
        extra={
            "user_id": str(user_id),
            "rule_id": str(rule_id),
            "days": days,
            "limit": limit,
            "created_matches": created,
        },
    )

    return created
