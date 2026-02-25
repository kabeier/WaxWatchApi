from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.monetization.outbound import tracked_outbound_path
from app.services.matching import enrich_listing_mapping
from app.services.notifications import enqueue_from_event
from app.services.watch_rules import ensure_user_exists

logger = get_logger(__name__)


@contextmanager
def _ingest_transaction(db: Session):
    if db.in_transaction():
        with db.begin_nested():
            yield
        return

    with db.begin():
        yield


def normalize_title(s: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in s).split())


def upsert_listing(db: Session, payload: dict[str, Any]) -> tuple[models.Listing, bool, bool]:
    """
    Returns: (listing, created_listing, created_snapshot)
    """
    provider = models.Provider(payload["provider"])
    external_id = str(payload["external_id"])
    now = datetime.now(timezone.utc)

    created_listing = False
    created_snapshot = False

    listing = (
        db.query(models.Listing)
        .filter(models.Listing.provider == provider)
        .filter(models.Listing.external_id == external_id)
        .first()
    )

    if listing is None:
        insert_values = {
            "provider": provider,
            "external_id": external_id,
            "url": payload["url"],
            "title": payload["title"],
            "normalized_title": normalize_title(payload["title"]),
            "price": float(payload["price"]),
            "currency": payload.get("currency") or "USD",
            "condition": payload.get("condition"),
            "seller": payload.get("seller"),
            "location": payload.get("location"),
            "status": models.ListingStatus.active,
            "discogs_release_id": payload.get("discogs_release_id"),
            "discogs_master_id": payload.get("discogs_master_id"),
            "first_seen_at": now,
            "last_seen_at": now,
            "raw": payload.get("raw"),
        }

        stmt = (
            pg_insert(models.Listing)
            .values(**insert_values)
            .on_conflict_do_nothing(index_elements=["provider", "external_id"])
            .returning(models.Listing.id)
        )

        inserted_id = db.execute(stmt).scalar_one_or_none()

        if inserted_id is not None:
            created_listing = True
            listing = db.get(models.Listing, inserted_id)
            if listing is None:
                listing = (
                    db.query(models.Listing)
                    .filter(models.Listing.provider == provider)
                    .filter(models.Listing.external_id == external_id)
                    .first()
                )

            # Always snapshot on create
            if listing is not None:
                db.add(
                    models.PriceSnapshot(
                        listing_id=listing.id,
                        price=float(listing.price),
                        currency=listing.currency,
                        recorded_at=now,
                    )
                )
                created_snapshot = True

            db.flush()
            return listing, created_listing, created_snapshot

        # Race
        # Load it and proceed to update path.
        listing = (
            db.query(models.Listing)
            .filter(models.Listing.provider == provider)
            .filter(models.Listing.external_id == external_id)
            .first()
        )
        if listing is None:
            # If this happens, your uniqueness/index_elements don't match reality.
            raise RuntimeError("Listing insert conflict but listing not found (check unique constraint).")

    # Update path
    old_price = float(listing.price)
    old_currency = listing.currency

    listing.url = payload["url"]
    listing.title = payload["title"]
    listing.normalized_title = normalize_title(payload["title"])
    listing.currency = payload.get("currency") or listing.currency
    listing.condition = payload.get("condition")
    listing.seller = payload.get("seller")
    listing.location = payload.get("location")
    listing.discogs_release_id = payload.get("discogs_release_id")
    listing.discogs_master_id = payload.get("discogs_master_id")
    listing.last_seen_at = now
    listing.raw = payload.get("raw")

    new_price = float(payload["price"])
    listing.price = new_price
    new_currency = listing.currency

    db.add(listing)
    db.flush()

    # Snapshot rule: create snapshot when price OR currency changes.
    if new_price != old_price or new_currency != old_currency:
        db.add(
            models.PriceSnapshot(
                listing_id=listing.id,
                price=new_price,
                currency=listing.currency,
                recorded_at=now,
            )
        )
        created_snapshot = True
        db.flush()

    return listing, False, created_snapshot


def match_listing_to_rules(db: Session, *, user_id: UUID, listing: models.Listing) -> int:
    """
    Checks active rules and release watches for this user and creates NEW_MATCH events.
    Returns number of new matches created.
    """
    created = 0
    title_norm = listing.normalized_title or normalize_title(listing.title)
    user_currency = db.query(models.User.currency).filter(models.User.id == user_id).scalar()

    rules = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.user_id == user_id)
        .filter(models.WatchSearchRule.is_active.is_(True))
        .all()
    )

    for rule in rules:
        if _rule_matches_listing(rule, listing, title_norm, user_currency=user_currency):
            created += _create_match_if_needed(db, user_id=user_id, rule=rule, listing=listing)

    release_watches = (
        db.query(models.WatchRelease)
        .filter(models.WatchRelease.user_id == user_id)
        .filter(models.WatchRelease.is_active.is_(True))
        .all()
    )
    for watch in release_watches:
        if _watch_release_matches_listing(watch, listing):
            created += _create_release_match_event_if_needed(
                db, user_id=user_id, watch=watch, listing=listing
            )

    return created


def _rule_matches_listing(
    rule: models.WatchSearchRule,
    listing: models.Listing,
    normalized_title: str,
    *,
    user_currency: str | None = None,
) -> bool:
    q = rule.query or {}

    sources = q.get("sources")
    if isinstance(sources, list) and sources:
        allowed = [str(s).strip().lower() for s in sources if str(s).strip()]
        if listing.provider.value not in allowed:
            logger.debug(
                "match.skip.source_not_allowed",
                extra={"rule_id": str(rule.id), "provider": listing.provider.value, "allowed": allowed},
            )
            return False

    max_price = q.get("max_price")
    if isinstance(max_price, (int | float)):
        rule_currency_raw = q.get("currency") or user_currency
        rule_currency = str(rule_currency_raw).strip().upper() if rule_currency_raw else None
        listing_currency = str(listing.currency).strip().upper()

        if not rule_currency:
            logger.debug(
                "match.skip.price_currency_unknown",
                extra={
                    "rule_id": str(rule.id),
                    "listing_currency": listing_currency,
                    "max_price": float(max_price),
                },
            )
            return False

        if listing_currency != rule_currency:
            logger.debug(
                "match.skip.price_currency_mismatch_non_comparable",
                extra={
                    "rule_id": str(rule.id),
                    "listing_currency": listing_currency,
                    "rule_currency": rule_currency,
                    "max_price": float(max_price),
                },
            )
            return False

        if float(listing.price) > float(max_price):
            logger.debug(
                "match.skip.price_too_high",
                extra={"rule_id": str(rule.id), "price": float(listing.price), "max_price": float(max_price)},
            )
            return False

    keywords = q.get("keywords")
    if isinstance(keywords, list) and keywords:
        kws = [str(k).strip().lower() for k in keywords if str(k).strip()]
        if not kws:
            logger.debug(
                "match.skip.invalid_keywords",
                extra={"rule_id": str(rule.id), "keywords": keywords},
            )
            return False
        for kw in kws:
            if kw not in normalized_title:
                logger.debug(
                    "match.skip.keyword_missing",
                    extra={"rule_id": str(rule.id), "keyword": kw, "title_norm": normalized_title},
                )
                return False

    return True


def _watch_release_matches_listing(watch: models.WatchRelease, listing: models.Listing) -> bool:
    if watch.match_mode == "master_release":
        return (
            watch.discogs_master_id is not None
            and listing.discogs_master_id is not None
            and int(watch.discogs_master_id) == int(listing.discogs_master_id)
        )

    return listing.discogs_release_id is not None and int(watch.discogs_release_id) == int(
        listing.discogs_release_id
    )


def _create_release_match_event_if_needed(
    db: Session,
    *,
    user_id: UUID,
    watch: models.WatchRelease,
    listing: models.Listing,
) -> int:
    existing_event = (
        db.query(models.Event.id)
        .filter(models.Event.user_id == user_id)
        .filter(models.Event.type == models.EventType.NEW_MATCH)
        .filter(models.Event.watch_release_id == watch.id)
        .filter(models.Event.listing_id == listing.id)
        .first()
    )
    if existing_event is not None:
        return 0

    now = datetime.now(timezone.utc)
    public_url = tracked_outbound_path(provider=listing.provider.value, listing_id=listing.id) or listing.url
    event = models.Event(
        user_id=user_id,
        type=models.EventType.NEW_MATCH,
        watch_release_id=watch.id,
        listing_id=listing.id,
        payload={
            "match_type": "watch_release",
            "watch_release_title": watch.title,
            "watch_match_mode": watch.match_mode,
            "listing_title": listing.title,
            "provider": listing.provider.value,
            "url": public_url,
        },
        created_at=now,
    )
    db.add(event)
    db.flush()
    enqueue_from_event(db, event=event)
    return 1


def _create_match_if_needed(
    db: Session,
    *,
    user_id: UUID,
    rule: models.WatchSearchRule,
    listing: models.Listing,
) -> int:
    """
    Create WatchMatch + Event if not already present.
    """
    now = datetime.now(timezone.utc)

    # Insert match idempotently
    stmt = (
        pg_insert(models.WatchMatch)
        .values(
            rule_id=rule.id,
            listing_id=listing.id,
            matched_at=now,
            match_context={"reason": "rule_filters_passed"},
        )
        .on_conflict_do_nothing(index_elements=["rule_id", "listing_id"])
        .returning(models.WatchMatch.id)
    )

    inserted_match_id = db.execute(stmt).scalar_one_or_none()
    if inserted_match_id is None:
        return 0

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
            "url": tracked_outbound_path(provider=listing.provider.value, listing_id=listing.id)
            or listing.url,
        },
        created_at=now,
    )
    db.add(ev)
    db.flush()
    enqueue_from_event(db, event=ev)
    return 1


def ingest_and_match(
    db: Session,
    *,
    user_id: UUID,
    listing_payload: dict[str, Any],
) -> tuple[models.Listing, bool, bool, int]:
    """
    Transaction-safe ingest.

    Uses a SAVEPOINT when already in a transaction to avoid nesting errors in tests
    and batched runner contexts, while still avoiding any inner commits.
    """
    with _ingest_transaction(db):
        ensure_user_exists(db, user_id)

        listing, created_listing, created_snapshot = upsert_listing(db, listing_payload)
        enrich_listing_mapping(db, user_id=user_id, listing=listing)
        created_matches = match_listing_to_rules(db, user_id=user_id, listing=listing)

    return listing, created_listing, created_snapshot, created_matches
