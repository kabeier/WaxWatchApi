from __future__ import annotations

from uuid import UUID


def tracked_outbound_path(*, provider: str, listing_id: UUID) -> str:
    provider_key = (provider or "").strip().lower()
    if provider_key == "ebay":
        return f"/api/outbound/ebay/{listing_id}"
    return ""
