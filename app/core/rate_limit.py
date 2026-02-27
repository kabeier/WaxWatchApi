from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from app.core.config import settings

ScopeName = Literal[
    "global_authenticated",
    "global_anonymous",
    "auth_endpoints",
    "search",
    "watch_rules",
    "discogs",
    "stream_events",
]


class RateLimitExceededError(Exception):
    def __init__(self, *, scope: ScopeName, retry_after_seconds: int):
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds
        super().__init__("rate limit exceeded")


@dataclass(frozen=True)
class RateLimitPolicy:
    limit: int
    burst: int
    window_seconds: int = 60

    @property
    def capacity(self) -> int:
        return self.limit + self.burst


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, policy: RateLimitPolicy) -> tuple[bool, int]:
        now = time.monotonic()
        window_start = now - policy.window_seconds

        with self._lock:
            events = self._events[key]
            while events and events[0] <= window_start:
                events.popleft()

            if len(events) >= policy.capacity:
                retry_after = max(int(events[0] + policy.window_seconds - now), 1)
                return False, retry_after

            events.append(now)
            return True, 0


_RATE_LIMITER = SlidingWindowRateLimiter()


def _client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
        if client_ip:
            return client_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _token_fingerprint(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header[7:].strip()
    if not token:
        return None

    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def _scope_policies() -> dict[ScopeName, RateLimitPolicy]:
    return {
        "global_authenticated": RateLimitPolicy(
            limit=settings.rate_limit_global_authenticated_rpm,
            burst=settings.rate_limit_global_authenticated_burst,
        ),
        "global_anonymous": RateLimitPolicy(
            limit=settings.rate_limit_global_anonymous_rpm,
            burst=settings.rate_limit_global_anonymous_burst,
        ),
        "auth_endpoints": RateLimitPolicy(
            limit=settings.rate_limit_auth_endpoint_rpm,
            burst=settings.rate_limit_auth_endpoint_burst,
        ),
        "search": RateLimitPolicy(
            limit=settings.rate_limit_search_rpm,
            burst=settings.rate_limit_search_burst,
        ),
        "watch_rules": RateLimitPolicy(
            limit=settings.rate_limit_watch_rules_rpm,
            burst=settings.rate_limit_watch_rules_burst,
        ),
        "discogs": RateLimitPolicy(
            limit=settings.rate_limit_discogs_rpm,
            burst=settings.rate_limit_discogs_burst,
        ),
        "stream_events": RateLimitPolicy(
            limit=settings.rate_limit_stream_events_rpm,
            burst=settings.rate_limit_stream_events_burst,
        ),
    }


def enforce_rate_limit(
    request: Request, *, scope: ScopeName, require_authenticated_principal: bool = False
) -> None:
    if not settings.rate_limit_enabled:
        return

    identifier = _token_fingerprint(request)
    if identifier is None:
        principal_key = f"anon:{_client_identifier(request)}"
    else:
        principal_key = f"auth:{identifier}"

    policy = _scope_policies()[scope]
    allowed, retry_after = _RATE_LIMITER.check(f"{scope}:{principal_key}", policy)
    if not allowed:
        raise RateLimitExceededError(scope=scope, retry_after_seconds=retry_after)


def enforce_global_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return

    token_key = _token_fingerprint(request)
    if token_key is None:
        enforce_rate_limit(request, scope="global_anonymous", require_authenticated_principal=False)
    else:
        enforce_rate_limit(request, scope="global_authenticated", require_authenticated_principal=True)


def is_rate_limit_exempt_path(path: str) -> bool:
    if path in {"/healthz", "/readyz", "/metrics"}:
        return True

    return False


def reset_rate_limiter_state() -> None:
    global _RATE_LIMITER
    _RATE_LIMITER = SlidingWindowRateLimiter()
