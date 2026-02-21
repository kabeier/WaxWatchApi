from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import models
from app.providers.mock import MockProvider
from app.services.ingest import ingest_and_match
from app.providers.registry import PROVIDERS
from app.providers.base import ProviderError

@dataclass
class RuleRunSummary:
    rule_id: UUID
    fetched: int
    listings_created: int
    snapshots_created: int
    matches_created: int


def _providers_for_rule(rule: models.WatchSearchRule) -> list[str]:
    q = rule.query or {}
    sources = q.get("sources")
    if isinstance(sources, list) and sources:
        return [str(s).strip().lower() for s in sources if str(s).strip()]
    # default sources if none specified
    return ["ebay"]


def run_rule_once(db: Session, *, user_id: UUID, rule_id: UUID, limit: int = 20) -> RuleRunSummary:
    rule = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.id == rule_id)
        .filter(models.WatchSearchRule.user_id == user_id)
        .first()
    )
    if not rule:
        raise ValueError("Rule not found for user")

    if not rule.is_active:
        return RuleRunSummary(rule_id=rule_id, fetched=0, listings_created=0, snapshots_created=0, matches_created=0)

    fetched = 0
    listings_created = 0
    snapshots_created = 0
    matches_created = 0

    sources = _providers_for_rule(rule)

    for source in sources:
        provider_cls = PROVIDERS.get(source)
        if not provider_cls:
            continue

        provider_client = provider_cls()

        try:
            provider_query = dict(rule.query or {})
            provider_query["_seed"] = str(rule.id)
            provider_listings = provider_client.search(query=provider_query, limit=limit)
            
        except ProviderError:
            continue
        
        fetched += len(provider_listings)

        for pl in provider_listings:
            listing_payload = {
                "provider": pl.provider,
                "external_id": pl.external_id,
                "url": pl.url,
                "title": pl.title,
                "price": pl.price,
                "currency": pl.currency,
                "condition": pl.condition,
                "seller": pl.seller,
                "location": pl.location,
                "discogs_release_id": pl.discogs_release_id,
                "raw": pl.raw,
            }

            listing, created_listing, created_snapshot, created_matches = ingest_and_match(
                db,
                user_id=user_id,
                listing_payload=listing_payload,
            )

            if created_listing:
                listings_created += 1
            if created_snapshot:
                snapshots_created += 1
            matches_created += created_matches

    return RuleRunSummary(
        rule_id=rule_id,
        fetched=fetched,
        listings_created=listings_created,
        snapshots_created=snapshots_created,
        matches_created=matches_created,
    )