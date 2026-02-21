from __future__ import annotations

import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models
from app.providers.base import ProviderClient, ProviderListing, ProviderError


BASE_URL = "https://api.discogs.com"


class DiscogsClient(ProviderClient):
    name = "discogs"

    def __init__(self) -> None:
        self._headers = {
            "User-Agent": settings.discogs_user_agent,
            "Authorization": f"Discogs token={settings.discogs_token}",
        }

    def search(self, *, query: dict[str, Any], limit: int = 20) -> list[ProviderListing]:
        keywords = query.get("keywords") or []
        search_query = " ".join(keywords) if keywords else ""

        params = {
            "q": search_query,
            "type": "release",
            "per_page": min(limit, 50),
        }

        start = time.perf_counter()

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{BASE_URL}/database/search",
                    headers=self._headers,
                    params=params,
                )

            duration_ms = int((time.perf_counter() - start) * 1000)

            if response.status_code != 200:
                raise ProviderError(f"Discogs error {response.status_code}: {response.text}")

            data = response.json()
            results = data.get("results", [])

            listings: list[ProviderListing] = []

            for r in results:
                listings.append(
                    ProviderListing(
                        provider="discogs",
                        external_id=str(r.get("id")),
                        url=r.get("uri") or r.get("resource_url") or "",
                        title=r.get("title") or "",
                        price=0.0,  # Discogs search doesn’t include marketplace price
                        currency="USD",
                        condition=None,
                        seller=None,
                        location=None,
                        discogs_release_id=r.get("id"),
                        raw=r,
                    )
                )

            return listings

        except httpx.RequestError as e:
            raise ProviderError(f"Network error: {e}") from e