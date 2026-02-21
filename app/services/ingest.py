from __future__ import annotations

from datetime import datetime, UTC
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.services.watch_rules import ensure_user_exists


def normalize_title(s: str) -> str:
    # simple v1 normalizer (good enough for matching + trigram)
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in s).split())


def upsert_listing(db: Session, payload: dict[str, Any]) -> tuple[models.Listing, bool, bool]:
    """
    Returns: (listing, created_listing, created_snapshot)
    """
    provider = models.Provider(payload["provider"])
    external_id = payload["external_id"]

    now = datetime.now(UTC)

    listing = (
        db.query(models.Listing)
        .filter(models.Listing.provider == provider)
        .filter(models.Listing.external_id == external_id)
        .first()
    )

    created_listing = False
    created_snapshot = False

    if listing is None:
        listing = models.Listing(
            provider=provider,
            external_id=external_id,
            url=payload["url"],
            title=payload["title"],
            normalized_title=normalize_title(payload["title"]),
            price=float(payload["price"]),
            currency=payload.get("currency") or "USD",
            condition=payload.get("condition"),
            seller=payload.get("seller"),
            location=payload.get("location"),
            status=models.ListingStatus.active,
            discogs_release_id=payload.get("discogs_release_id"),
            first_seen_at=now,
            last_seen_at=now,
            raw=payload.get("raw"),
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        created_listing = True

        # always snapshot on create
        db.add(models.PriceSnapshot(listing_id=listing.id, price=listing.price, currency=listing.currency, recorded_at=now))
        db.commit()
        created_snapshot = True

    else:
        # update fields + track price changes
        old_price = float(listing.price)

        listing.url = payload["url"]
        listing.title = payload["title"]
        listing.normalized_title = normalize_title(payload["title"])
        listing.currency = payload.get("currency") or listing.currency
        listing.condition = payload.get("condition")
        listing.seller = payload.get("seller")
        listing.location = payload.get("location")
        listing.discogs_release_id = payload.get("discogs_release_id")
        listing.last_seen_at = now
        listing.raw = payload.get("raw")

        new_price = float(payload["price"])
        listing.price = new_price

        db.add(listing)
        db.commit()
        db.refresh(listing)

        # snapshot rule: snapshot if price changed (you can change this later)
        if new_price != old_price:
            db.add(models.PriceSnapshot(listing_id=listing.id, price=new_price, currency=listing.currency, recorded_at=now))
            db.commit()
            created_snapshot = True

    return listing, created_listing, created_snapshot


def match_listing_to_rules(db: Session, *, user_id: UUID, listing: models.Listing) -> int:
    """
    Checks active rules for this user and creates WatchMatch + NEW_MATCH Event.
    Returns number of new matches created.
    """
    created = 0
    title = (listing.normalized_title or normalize_title(listing.title))

    # Load active rules
    rules = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.user_id == user_id)
        .filter(models.WatchSearchRule.is_active.is_(True))
        .all()
    )

    for rule in rules:
        if _rule_matches_listing(rule, listing, title):
            created += _create_match_if_needed(db, user_id=user_id, rule=rule, listing=listing)

    return created


def _rule_matches_listing(rule, listing, normalized_title):
    q = rule.query or {}

    sources = q.get("sources")
    if isinstance(sources, list) and sources:
        allowed = [str(s).strip().lower() for s in sources]
        if listing.provider.value not in allowed:
            print("NO MATCH: source", listing.provider.value, "not in", allowed)
            return False

    max_price = q.get("max_price")
    if isinstance(max_price, (int, float)):
        if float(listing.price) > float(max_price):
            print("NO MATCH: price", listing.price, ">", max_price)
            return False

    keywords = q.get("keywords")
    if isinstance(keywords, list) and keywords:
        kws = [str(k).strip().lower() for k in keywords if str(k).strip()]
        for kw in kws:
            if kw not in normalized_title:
                print("NO MATCH: keyword", kw, "not in", normalized_title)
                return False

    print("MATCH:", rule.id)
    return True

def _create_match_if_needed(db: Session, *, user_id: UUID, rule: models.WatchSearchRule, listing: models.Listing) -> int:
    existing = (
        db.query(models.WatchMatch)
        .filter(models.WatchMatch.rule_id == rule.id)
        .filter(models.WatchMatch.listing_id == listing.id)
        .first()
    )
    if existing:
        return 0

    now = datetime.now(UTC)
    match = models.WatchMatch(
        rule_id=rule.id,
        listing_id=listing.id,
        matched_at=now,
        match_context={"reason": "rule_filters_passed"},
    )
    db.add(match)

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
        },
        created_at=now,
    )
    db.add(ev)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return 0

    return 1


def ingest_and_match(db: Session, *, user_id: UUID, listing_payload: dict[str, Any]) -> tuple[models.Listing, bool, bool, int]:
    ensure_user_exists(db, user_id)

    listing, created_listing, created_snapshot = upsert_listing(db, listing_payload)
    created_matches = match_listing_to_rules(db, user_id=user_id, listing=listing)

    return listing, created_listing, created_snapshot, created_matches