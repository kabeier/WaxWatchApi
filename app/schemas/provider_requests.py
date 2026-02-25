from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProviderRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    endpoint: str
    method: str
    status_code: int | None
    duration_ms: int | None
    error: str | None
    meta: dict[str, Any] | None
    created_at: datetime


class ProviderRequestSummaryOut(BaseModel):
    provider: str
    total_requests: int
    error_requests: int
    avg_duration_ms: float | None


class ProviderRequestAdminOut(ProviderRequestOut):
    id: UUID
    user_id: UUID
