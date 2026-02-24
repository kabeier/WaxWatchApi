from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class DiscogsConnectIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "external_user_id": "discogs_user_2048",
                "access_token": "discogs_access_token_redacted",
                "token_metadata": {"scope": "identity wantlist inventory", "token_type": "oauth"},
            }
        }
    )

    external_user_id: str = Field(min_length=1, max_length=120)
    access_token: str | None = Field(default=None, min_length=1)
    token_metadata: dict[str, Any] | None = None

    @field_serializer("access_token", when_used="always")
    def _serialize_access_token(self, access_token: str | None) -> str | None:
        if not access_token:
            return access_token
        return "***redacted***"


class DiscogsOAuthStartIn(BaseModel):
    scopes: list[str] | None = Field(default=None, min_length=1)


class DiscogsOAuthStartOut(BaseModel):
    provider: str
    authorize_url: str
    state: str
    scopes: list[str]
    expires_at: datetime


class DiscogsOAuthCallbackIn(BaseModel):
    state: str = Field(min_length=8)
    code: str = Field(min_length=1)


class DiscogsDisconnectIn(BaseModel):
    revoke: bool = True


class DiscogsDisconnectOut(BaseModel):
    provider: str
    disconnected: bool


class DiscogsConnectOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider": "discogs",
                "external_user_id": "discogs_user_2048",
                "connected": True,
                "connected_at": "2026-01-10T15:34:12.123456+00:00",
            }
        }
    )

    provider: str
    external_user_id: str
    connected: bool
    connected_at: datetime


class DiscogsStatusOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "connected": True,
                "provider": "discogs",
                "external_user_id": "discogs_user_2048",
                "connected_at": "2026-01-10T15:34:12.123456+00:00",
                "has_access_token": True,
            }
        }
    )

    connected: bool
    provider: str
    external_user_id: str | None = None
    connected_at: datetime | None = None
    has_access_token: bool = False


class DiscogsImportIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"source": "both"}})

    source: Literal["wantlist", "collection", "both"] = "both"


class DiscogsImportJobOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "b9f9402e-6f7a-4ced-9ca8-a0f6306ee4ef",
                "user_id": "8f2a5009-c0a2-4f90-8f1b-c1716c26bf06",
                "provider": "discogs",
                "import_scope": "both",
                "status": "completed",
                "cursor": None,
                "page": 3,
                "processed_count": 200,
                "imported_count": 200,
                "created_count": 140,
                "updated_count": 60,
                "error_count": 0,
                "errors": [],
                "started_at": "2026-01-20T10:00:00+00:00",
                "completed_at": "2026-01-20T10:00:07+00:00",
                "created_at": "2026-01-20T10:00:00+00:00",
                "updated_at": "2026-01-20T10:00:07+00:00",
            }
        },
    )

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
