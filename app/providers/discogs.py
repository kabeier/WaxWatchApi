from __future__ import annotations

import time
from random import random
from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import (
    ProviderCapabilityContract,
    ProviderClient,
    ProviderError,
    ProviderListing,
    ProviderPaginationModel,
    ProviderRequestLog,
    ProviderRequestLogger,
)

BASE_URL = "https://api.discogs.com"


class DiscogsClient(ProviderClient):
    name = "discogs"
    default_endpoint = "/database/search"
    capability_contract = ProviderCapabilityContract(
        supports_search=True,
        requires_auth=True,
        rate_limits_documented=True,
        listing_completeness="release-level metadata without marketplace price",
        pagination_model=ProviderPaginationModel.OFFSET,
    )

    def __init__(self, *, request_logger: ProviderRequestLogger | None = None) -> None:
        self.last_request_meta: dict[str, Any] | None = None
        self.last_duration_ms: int | None = None
        self._request_logger = request_logger
        self._headers = {
            "User-Agent": settings.discogs_user_agent,
            "Authorization": f"Discogs token={settings.discogs_token}",
        }

    def _log_request(
        self,
        *,
        endpoint: str,
        method: str,
        status_code: int | None,
        duration_ms: int | None,
        error: str | None,
        meta: dict[str, Any] | None,
    ) -> None:
        if self._request_logger is None:
            return
        self._request_logger(
            ProviderRequestLog(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                duration_ms=duration_ms,
                error=error,
                meta=meta,
            )
        )

    @staticmethod
    def _parse_retry_after_seconds(raw: str | None) -> float | None:
        if not raw:
            return None
        try:
            return max(float(raw), 0.0)
        except ValueError:
            return None

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _compute_backoff_seconds(self, attempt: int) -> float:
        base = max(settings.discogs_retry_base_delay_ms, 1) / 1000.0
        max_delay = max(settings.discogs_retry_max_delay_ms, settings.discogs_retry_base_delay_ms) / 1000.0
        capped = min(base * (2 ** max(attempt - 1, 0)), max_delay)
        return capped * (0.5 + random())

    def _response_meta(
        self,
        *,
        attempt: int,
        attempts: int,
        retry_after_seconds: float | None,
        headers: dict[str, str | None],
    ) -> dict[str, Any]:
        return {
            "attempt": attempt,
            "attempts_total": attempts,
            "max_attempts": attempts,
            "retry_after_seconds": retry_after_seconds,
            "headers": headers,
            "rate_limit": headers.get("X-Discogs-Ratelimit"),
            "rate_limit_remaining": headers.get("X-Discogs-Ratelimit-Remaining"),
            "rate_limit_used": headers.get("X-Discogs-Ratelimit-Used"),
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
        attempts = max(settings.discogs_max_attempts, 1)
        final_meta: dict[str, Any] | None = None

        try:
            with httpx.Client(timeout=settings.discogs_timeout_seconds) as client:
                resp: httpx.Response | None = None
                for attempt in range(1, attempts + 1):
                    attempt_start = time.perf_counter()
                    try:
                        resp = client.get(url, headers=self._headers, params=params)
                    except httpx.RequestError as e:
                        duration_ms = int((time.perf_counter() - attempt_start) * 1000)
                        final_meta = self._response_meta(
                            attempt=attempt,
                            attempts=attempts,
                            retry_after_seconds=None,
                            headers={},
                        )
                        final_meta["retryable"] = True
                        self._log_request(
                            endpoint=endpoint,
                            method=method,
                            status_code=None,
                            duration_ms=duration_ms,
                            error=f"Discogs network error: {e}",
                            meta=final_meta,
                        )
                        if attempt < attempts:
                            time.sleep(self._compute_backoff_seconds(attempt))
                            continue

                        duration_ms = int((time.perf_counter() - start) * 1000)
                        raise ProviderError(
                            f"Discogs network error: {e}",
                            status_code=None,
                            meta=final_meta,
                            endpoint=endpoint,
                            method=method,
                            duration_ms=duration_ms,
                        ) from e

                    retry_after_seconds = self._parse_retry_after_seconds(resp.headers.get("Retry-After"))
                    header_meta = {
                        "Retry-After": resp.headers.get("Retry-After"),
                        "X-Discogs-Ratelimit": resp.headers.get("X-Discogs-Ratelimit"),
                        "X-Discogs-Ratelimit-Remaining": resp.headers.get("X-Discogs-Ratelimit-Remaining"),
                        "X-Discogs-Ratelimit-Used": resp.headers.get("X-Discogs-Ratelimit-Used"),
                    }
                    final_meta = self._response_meta(
                        attempt=attempt,
                        attempts=attempts,
                        retry_after_seconds=retry_after_seconds,
                        headers=header_meta,
                    )
                    duration_ms = int((time.perf_counter() - attempt_start) * 1000)
                    self._log_request(
                        endpoint=endpoint,
                        method=method,
                        status_code=resp.status_code,
                        duration_ms=duration_ms,
                        error=None if resp.status_code == 200 else f"Discogs error {resp.status_code}",
                        meta=final_meta,
                    )

                    if resp.status_code == 200:
                        break

                    if attempt < attempts and self._is_retryable_status(resp.status_code):
                        time.sleep(
                            retry_after_seconds
                            if retry_after_seconds is not None
                            else self._compute_backoff_seconds(attempt)
                        )
                        continue

                    duration_ms = int((time.perf_counter() - start) * 1000)
                    raise ProviderError(
                        f"Discogs error {resp.status_code}",
                        status_code=resp.status_code,
                        meta=final_meta,
                        endpoint=endpoint,
                        method=method,
                        duration_ms=duration_ms,
                    )

            duration_ms = int((time.perf_counter() - start) * 1000)
            self.last_request_meta = final_meta
            self.last_duration_ms = duration_ms

            if resp is None:
                raise ProviderError(
                    "Discogs empty response", status_code=None, endpoint=endpoint, method=method
                )

            data = resp.json()
            results = data.get("results", [])

            out: list[ProviderListing] = []
            for r in results:
                release_id = r.get("id")
                master_id = r.get("master_id")
                external_id = str(release_id).strip() if release_id is not None else ""
                title = str(r.get("title") or "").strip()
                listing_url = str(r.get("uri") or r.get("resource_url") or "").strip()
                if not external_id or not title or not listing_url:
                    continue

                out.append(
                    ProviderListing(
                        provider="discogs",
                        external_id=external_id,
                        url=listing_url,
                        title=title,
                        price=0.0,
                        currency="USD",
                        discogs_release_id=release_id,
                        discogs_master_id=master_id,
                        raw=r,
                    )
                )

            return out

        except ProviderError as e:
            self.last_request_meta = e.meta
            self.last_duration_ms = e.duration_ms
            raise
