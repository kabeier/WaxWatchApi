from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DiscogsConnectIn(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=120)
    access_token: str | None = Field(default=None, min_length=1)
    token_metadata: dict[str, Any] | None = None


class DiscogsConnectOut(BaseModel):
    provider: str
    external_user_id: str
    connected: bool
    connected_at: datetime


class DiscogsStatusOut(BaseModel):
    connected: bool
    provider: str
    external_user_id: str | None = None
    connected_at: datetime | None = None
    has_access_token: bool = False


class DiscogsImportIn(BaseModel):
    source: Literal["wantlist", "collection", "both"] = "both"


class DiscogsImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    provider: str
    import_scope: str
    status: str

    cursor: str | None
    page: int

    processed_count: int
    imported_count: int
    created_count: int
    updated_count: int
    error_count: int
    errors: list[dict[str, Any]] | None

    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
