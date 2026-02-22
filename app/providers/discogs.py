from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ProviderClient, ProviderError, ProviderListing

BASE_URL = "https://api.discogs.com"


class DiscogsClient(ProviderClient):
    name = "discogs"
    default_endpoint = "/database/search"

    def __init__(self) -> None:
        self._headers = {
            "User-Agent": settings.discogs_user_agent,
            "Authorization": f"Discogs token={settings.discogs_token}",
        }

    def search(self, *, query: dict[str, Any], limit: int = 20) -> list[ProviderListing]:
        keywords = query.get("keywords") or []
        q = " ".join([str(k).strip() for k in keywords if str(k).strip()])

        endpoint = "/database/search"
        url = f"{BASE_URL}{endpoint}"
        method = "GET"

        params = {
            "q": q,
            "type": "release",
            "per_page": min(limit, 50),
        }

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers, params=params)

            duration_ms = int((time.perf_counter() - start) * 1000)

            meta = {
                "rate_limit": resp.headers.get("X-Discogs-Ratelimit"),
                "rate_limit_remaining": resp.headers.get("X-Discogs-Ratelimit-Remaining"),
                "rate_limit_used": resp.headers.get("X-Discogs-Ratelimit-Used"),
            }

            if resp.status_code != 200:
                raise ProviderError(
                    f"Discogs error {resp.status_code}",
                    status_code=resp.status_code,
                    meta=meta,
                    endpoint=endpoint,
                    method=method,
                    duration_ms=duration_ms,
                )

            data = resp.json()
            results = data.get("results", [])

            out: list[ProviderListing] = []
            for r in results:
                release_id = r.get("id")
                out.append(
                    ProviderListing(
                        provider="discogs",
                        external_id=str(release_id),
                        url=r.get("uri") or r.get("resource_url") or "",
                        title=r.get("title") or "",
                        price=0.0,
                        currency="USD",
                        discogs_release_id=release_id,
                        raw=r,
                    )
                )

            return out

        except httpx.RequestError as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            raise ProviderError(
                f"Discogs network error: {e}",
                status_code=None,
                meta=None,
                endpoint=endpoint,
                method=method,
                duration_ms=duration_ms,
            ) from e
