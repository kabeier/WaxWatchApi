from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import models
from app.providers.base import ProviderError
from app.providers.registry import get_provider_class
from app.services.ingest import ingest_and_match
from app.services.provider_requests import log_provider_request


@dataclass
class RuleRunSummary:
    rule_id: UUID
    fetched: int
    listings_created: int
    snapshots_created: int
    matches_created: int


def _providers_for_rule(rule: models.WatchSearchRule) -> list[str]:
    sources = (rule.query or {}).get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"Rule {rule.id} has no sources (data invalid)")
    return [str(s).strip().lower() for s in sources if str(s).strip()]


def _endpoint_guess_for_source(source: str) -> str:
    # best-effort, for observability rows
    if source == "discogs":
        return "/database/search"
    if source == "ebay":
        return "/search"  # placeholder for later
    return "/unknown"


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
        return RuleRunSummary(
            rule_id=rule_id, fetched=0, listings_created=0, snapshots_created=0, matches_created=0
        )

    fetched = 0
    listings_created = 0
    snapshots_created = 0
    matches_created = 0

    sources = _providers_for_rule(rule)

    for source in sources:
        # raises ValueError if not in enum
        provider_enum = models.Provider(source)

        # registry swaps Discogs -> MockDiscogsClient in ENVIRONMENT=test
        provider_cls = get_provider_class(source)
        provider_client = provider_cls()

        provider_query = dict(rule.query or {})
        provider_query["_seed"] = str(rule.id)

        endpoint = getattr(provider_cls, "default_endpoint", "/unknown")

        try:
            provider_listings = provider_client.search(query=provider_query, limit=limit)
            duration_ms = getattr(provider_client, "last_duration_ms", None)
            meta = getattr(provider_client, "last_request_meta", None)
            log_provider_request(
                db,
                provider=provider_enum,
                endpoint=endpoint,
                method="GET",
                status_code=200,
                duration_ms=duration_ms,
                error=None,
                meta=meta,
            )
        except ProviderError as e:
            log_provider_request(
                db,
                provider=provider_enum,
                endpoint=e.endpoint or endpoint,
                method=e.method or "GET",
                status_code=e.status_code,
                duration_ms=e.duration_ms,
                error=str(e)[:500],
                meta=e.meta,
            )
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

            _, created_listing, created_snapshot, created_matches = ingest_and_match(
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
