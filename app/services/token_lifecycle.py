from __future__ import annotations

from datetime import datetime, timedelta, timezone

EXPIRY_SKEW = timedelta(seconds=30)


def is_token_expired(expires_at: datetime | None, *, now: datetime | None = None) -> bool:
    if expires_at is None:
        return False
    reference_time = now or datetime.now(timezone.utc)
    return expires_at <= reference_time


def should_refresh_access_token(
    *,
    refresh_token: str | None,
    access_token_expires_at: datetime | None,
    now: datetime | None = None,
    refresh_window: timedelta = EXPIRY_SKEW,
) -> bool:
    if not refresh_token:
        return False
    if access_token_expires_at is None:
        return True
    reference_time = now or datetime.now(timezone.utc)
    return access_token_expires_at <= (reference_time + refresh_window)
