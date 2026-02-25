from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import models
from app.providers.base import ProviderError, ProviderListing
from app.providers.registry import get_provider_class, list_available_providers
from app.schemas.search import SearchListingOut, SearchPagination, SearchQuery, SearchResponse
from app.services.provider_requests import log_provider_request
from app.services.watch_rules import create_watch_rule

_CONDITION_RANK: dict[str, int] = {
    "poor": 1,
    "fair": 2,
    "g": 3,
    "g+": 4,
    "vg": 5,
    "vg+": 6,
    "nm": 7,
    "m": 8,
}


def _default_providers() -> list[str]:
    supported: list[str] = []
    for key in list_available_providers():
        try:
            models.Provider(key)
        except ValueError:
            continue
        supported.append(key)
    return supported


def _resolve_providers(query: SearchQuery) -> list[str]:
    if query.providers:
        return query.providers
    return _default_providers()


def _condition_meets_minimum(condition: str | None, minimum: str | None) -> bool:
    if minimum is None:
        return True

    minimum_rank = _CONDITION_RANK.get(minimum.strip().lower())
    if minimum_rank is None:
        return True

    if condition is None:
        return False

    condition_rank = _CONDITION_RANK.get(condition.strip().lower())
    if condition_rank is None:
        return False

    return condition_rank >= minimum_rank


def _passes_filters(item: ProviderListing, query: SearchQuery) -> bool:
    if query.min_price is not None and item.price < query.min_price:
        return False
    if query.max_price is not None and item.price > query.max_price:
        return False
    if not _condition_meets_minimum(item.condition, query.min_condition):
        return False
    return True


def _to_listing_out(item: ProviderListing, *, listing_id: UUID | None = None) -> SearchListingOut:
    return SearchListingOut(
        id=f"{item.provider}:{item.external_id}",
        listing_id=listing_id,
        provider=item.provider,
        external_id=item.external_id,
        title=item.title,
        url=item.url,
        price=item.price,
        currency=item.currency,
        condition=item.condition,
        seller=item.seller,
        location=item.location,
        discogs_release_id=item.discogs_release_id,
    )


def run_search(db: Session, *, user_id: UUID, query: SearchQuery) -> SearchResponse:
    providers = _resolve_providers(query)
    providers_searched: list[str] = []
    provider_errors: dict[str, str] = {}
    listings: list[ProviderListing] = []

    per_provider_limit = query.page * query.page_size

    provider_query: dict[str, Any] = {
        "keywords": query.keywords,
        "min_price": query.min_price,
        "max_price": query.max_price,
        "min_condition": query.min_condition,
    }

    for provider_name in providers:
        provider_enum = models.Provider(provider_name)
        provider_cls = get_provider_class(provider_name)
        provider_client = provider_cls()
        endpoint = getattr(provider_cls, "default_endpoint", "/unknown")
        providers_searched.append(provider_name)

        try:
            provider_results = provider_client.search(query=provider_query, limit=per_provider_limit)
            log_provider_request(
                db,
                user_id=user_id,
                provider=provider_enum,
                endpoint=endpoint,
                method="GET",
                status_code=200,
                duration_ms=getattr(provider_client, "last_duration_ms", None),
                error=None,
                meta=getattr(provider_client, "last_request_meta", None),
            )
            listings.extend(provider_results)
        except ProviderError as exc:
            provider_errors[provider_name] = str(exc)
            log_provider_request(
                db,
                user_id=user_id,
                provider=provider_enum,
                endpoint=exc.endpoint or endpoint,
                method=exc.method or "GET",
                status_code=exc.status_code,
                duration_ms=exc.duration_ms,
                error=str(exc)[:500],
                meta=exc.meta,
            )
        except Exception as exc:  # pragma: no cover
            provider_errors[provider_name] = str(exc)
            log_provider_request(
                db,
                user_id=user_id,
                provider=provider_enum,
                endpoint=endpoint,
                method="GET",
                status_code=None,
                duration_ms=getattr(provider_client, "last_duration_ms", None),
                error=str(exc)[:500],
                meta={"exception_type": exc.__class__.__name__},
            )

    filtered = [item for item in listings if _passes_filters(item, query)]
    filtered.sort(key=lambda item: (item.price, item.provider, item.external_id))

    start = (query.page - 1) * query.page_size
    end = start + query.page_size
    page_items = filtered[start:end]

    persisted_listing_ids: dict[tuple[str, str], UUID] = {}
    if page_items:
        provider_external_pairs = {(item.provider, item.external_id) for item in page_items}
        provider_values = {provider for provider, _external_id in provider_external_pairs}
        external_ids = {external_id for _provider, external_id in provider_external_pairs}
        rows = (
            db.query(models.Listing)
            .filter(models.Listing.provider.in_([models.Provider(p) for p in provider_values]))
            .filter(models.Listing.external_id.in_(list(external_ids)))
            .all()
        )
        for row in rows:
            persisted_listing_ids[(row.provider.value, row.external_id)] = row.id

    out_items = [
        _to_listing_out(
            item,
            listing_id=persisted_listing_ids.get((item.provider, item.external_id)),
        )
        for item in page_items
    ]
    pagination = SearchPagination.build(
        page=query.page,
        page_size=query.page_size,
        total=len(filtered),
        returned=len(out_items),
    )

    return SearchResponse(
        items=out_items,
        pagination=pagination,
        providers_searched=providers_searched,
        provider_errors=provider_errors,
    )


def save_search_alert(
    db: Session,
    *,
    user_id: UUID,
    name: str,
    query: SearchQuery,
    poll_interval_seconds: int,
) -> models.WatchSearchRule:
    providers = _resolve_providers(query)
    rule_query: dict[str, Any] = {
        "keywords": query.keywords,
        "sources": providers,
        "min_price": query.min_price,
        "max_price": query.max_price,
        "min_condition": query.min_condition,
    }
    return create_watch_rule(
        db,
        user_id=user_id,
        name=name,
        query=rule_query,
        poll_interval_seconds=poll_interval_seconds,
    )
