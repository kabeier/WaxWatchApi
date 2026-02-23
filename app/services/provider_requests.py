from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def log_provider_request(
    db: Session,
    *,
    provider: models.Provider,
    endpoint: str,
    method: str = "GET",
    status_code: int | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    req = models.ProviderRequest(
        provider=provider,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        duration_ms=duration_ms,
        error=error,
        meta=meta,
        created_at=datetime.now(UTC),
    )
    db.add(req)
    db.flush()
