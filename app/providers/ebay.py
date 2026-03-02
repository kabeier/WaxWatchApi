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

OAUTH_BASE_URL = "https://api.ebay.com"
BROWSE_BASE_URL = "https://api.ebay.com"


class EbayClient(ProviderClient):
    name = "ebay"
    default_endpoint = "/buy/browse/v1/item_summary/search"
    capability_contract = ProviderCapabilityContract(
        supports_search=True,
        requires_auth=True,
        rate_limits_documented=True,
        listing_completeness="listing-level metadata with price and seller fields",
        pagination_model=ProviderPaginationModel.OFFSET,
    )

    def __init__(self, *, request_logger: ProviderRequestLogger | None = None) -> None:
        self.last_request_meta: dict[str, Any] | None = None
        self.last_duration_ms: int | None = None
        self._request_logger = request_logger

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
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    @staticmethod
    def _parse_retry_after_seconds(raw: str | None) -> float | None:
        if not raw:
            return None
        try:
            return max(float(raw), 0.0)
        except ValueError:
            return None

    def _compute_backoff_seconds(self, attempt: int) -> float:
        base = max(settings.ebay_retry_base_delay_ms, 1) / 1000.0
        max_delay = max(settings.ebay_retry_max_delay_ms, settings.ebay_retry_base_delay_ms) / 1000.0
        capped = min(base * (2 ** max(attempt - 1, 0)), max_delay)
        return capped * (0.5 + random())

    def _auth_token(self, client: httpx.Client) -> str:
        if not settings.ebay_client_id or not settings.ebay_client_secret:
            raise ProviderError(
                "eBay credentials missing",
                status_code=401,
                endpoint="/identity/v1/oauth2/token",
                method="POST",
            )

        token_endpoint = "/identity/v1/oauth2/token"
        token_url = f"{OAUTH_BASE_URL}{token_endpoint}"
        start = time.perf_counter()
        data = {
            "grant_type": "client_credentials",
            "scope": settings.ebay_oauth_scope,
        }

        try:
            resp = client.post(
                token_url,
                data=data,
                auth=(settings.ebay_client_id, settings.ebay_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._log_request(
                endpoint=token_endpoint,
                method="POST",
                status_code=None,
                duration_ms=duration_ms,
                error=f"eBay auth network error: {exc}",
                meta={"retryable": False},
            )
            raise ProviderError(
                f"eBay auth network error: {exc}",
                status_code=None,
                endpoint=token_endpoint,
                method="POST",
                duration_ms=duration_ms,
            ) from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
        auth_meta = {
            "request_id": resp.headers.get("x-ebay-c-request-id"),
            "rate_limit_remaining": resp.headers.get("x-ebay-c-remaining-request-limit"),
            "retry_after_seconds": self._parse_retry_after_seconds(resp.headers.get("Retry-After")),
        }
        if resp.status_code != 200:
            self._log_request(
                endpoint=token_endpoint,
                method="POST",
                status_code=resp.status_code,
                duration_ms=duration_ms,
                error=f"eBay auth error {resp.status_code}",
                meta=auth_meta,
            )
            raise ProviderError(
                f"eBay auth error {resp.status_code}",
                status_code=resp.status_code,
                endpoint=token_endpoint,
                method="POST",
                duration_ms=duration_ms,
                meta={"response": resp.text[:500]},
            )

        payload = resp.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            self._log_request(
                endpoint=token_endpoint,
                method="POST",
                status_code=resp.status_code,
                duration_ms=duration_ms,
                error="eBay auth missing access_token",
                meta={**auth_meta, "response_invalid": True},
            )
            raise ProviderError(
                "eBay auth missing access_token",
                status_code=resp.status_code,
                endpoint=token_endpoint,
                method="POST",
            )

        self._log_request(
            endpoint=token_endpoint,
            method="POST",
            status_code=resp.status_code,
            duration_ms=duration_ms,
            error=None,
            meta=auth_meta,
        )
        return token

    def search(self, *, query: dict[str, Any], limit: int = 20) -> list[ProviderListing]:
        keywords = query.get("keywords") or []
        q = " ".join([str(k).strip() for k in keywords if str(k).strip()])

        endpoint = self.default_endpoint
        url = f"{BROWSE_BASE_URL}{endpoint}"
        method = "GET"

        params = {
            "q": q,
            "limit": min(limit, 200),
        }

        start = time.perf_counter()
        attempts = max(settings.ebay_max_attempts, 1)
        final_meta: dict[str, Any] | None = None

        with httpx.Client(timeout=settings.ebay_timeout_seconds) as client:
            access_token = self._auth_token(client)
            headers = {
                "Authorization": f"Bearer {access_token}",
                "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace_id,
            }

            resp: httpx.Response | None = None
            for attempt in range(1, attempts + 1):
                attempt_start = time.perf_counter()
                try:
                    resp = client.get(url, params=params, headers=headers)
                except httpx.RequestError as exc:
                    duration_ms = int((time.perf_counter() - attempt_start) * 1000)
                    request_meta = {
                        "attempt": attempt,
                        "attempts_total": attempts,
                        "max_attempts": attempts,
                        "retryable": True,
                        "retry_after_seconds": None,
                        "request_id": None,
                        "rate_limit_remaining": None,
                    }
                    self._log_request(
                        endpoint=endpoint,
                        method=method,
                        status_code=None,
                        duration_ms=duration_ms,
                        error=f"eBay network error: {exc}",
                        meta=request_meta,
                    )
                    if attempt < attempts:
                        time.sleep(self._compute_backoff_seconds(attempt))
                        continue

                    duration_ms = int((time.perf_counter() - start) * 1000)
                    raise ProviderError(
                        f"eBay network error: {exc}",
                        status_code=None,
                        endpoint=endpoint,
                        method=method,
                        duration_ms=duration_ms,
                        meta={
                            "attempt": attempt,
                            "attempts_total": attempts,
                            "max_attempts": attempts,
                            "retryable": True,
                        },
                    ) from exc

                retry_after_seconds = self._parse_retry_after_seconds(resp.headers.get("Retry-After"))
                final_meta = {
                    "attempt": attempt,
                    "attempts_total": attempts,
                    "max_attempts": attempts,
                    "retry_after_seconds": retry_after_seconds,
                    "request_id": resp.headers.get("x-ebay-c-request-id"),
                    "rate_limit_remaining": resp.headers.get("x-ebay-c-remaining-request-limit"),
                }
                duration_ms = int((time.perf_counter() - attempt_start) * 1000)
                self._log_request(
                    endpoint=endpoint,
                    method=method,
                    status_code=resp.status_code,
                    duration_ms=duration_ms,
                    error=None if resp.status_code == 200 else f"eBay error {resp.status_code}",
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
                    f"eBay error {resp.status_code}",
                    status_code=resp.status_code,
                    endpoint=endpoint,
                    method=method,
                    duration_ms=duration_ms,
                    meta=final_meta,
                )

        duration_ms = int((time.perf_counter() - start) * 1000)
        self.last_duration_ms = duration_ms
        self.last_request_meta = final_meta

        if resp is None:
            raise ProviderError("eBay empty response", endpoint=endpoint, method=method)

        payload = resp.json()
        items = payload.get("itemSummaries", [])
        out: list[ProviderListing] = []

        for item in items:
            external_id = str(item.get("itemId") or "").strip()
            title = str(item.get("title") or "").strip()
            listing_url = str(item.get("itemWebUrl") or "").strip()
            price_value = (item.get("price") or {}).get("value")
            currency = str((item.get("price") or {}).get("currency") or "USD").strip()[:3]

            if not external_id or not title or not listing_url or price_value is None:
                continue

            try:
                price = float(price_value)
            except (TypeError, ValueError):
                continue

            out.append(
                ProviderListing(
                    provider=self.name,
                    external_id=external_id,
                    url=listing_url,
                    title=title,
                    price=price,
                    currency=currency,
                    condition=(item.get("condition") or None),
                    seller=((item.get("seller") or {}).get("username")),
                    location=(item.get("itemLocation") or {}).get("country"),
                    raw=item,
                )
            )

        return out
