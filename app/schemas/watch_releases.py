from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WatchReleaseBase(BaseModel):
    discogs_release_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    artist: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=0, le=9999)
    target_price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    min_condition: str | None = Field(default=None, max_length=30)
    is_active: bool = True


class WatchReleaseCreate(WatchReleaseBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "discogs_release_id": 249393,
                "title": "Selected Ambient Works 85-92",
                "artist": "Aphex Twin",
                "year": 1992,
                "target_price": 35,
                "currency": "USD",
                "min_condition": "VG+",
                "is_active": True,
            }
        }
    )


class WatchReleaseUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"target_price": 30, "currency": "USD", "min_condition": "NM", "is_active": True}
        }
    )

    discogs_release_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    artist: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=0, le=9999)
    target_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    min_condition: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None


class WatchReleaseOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "6608868d-f10f-4a5e-a38a-2e9fa5063f85",
                "user_id": "8f2a5009-c0a2-4f90-8f1b-c1716c26bf06",
                "discogs_release_id": 249393,
                "title": "Selected Ambient Works 85-92",
                "artist": "Aphex Twin",
                "year": 1992,
                "target_price": 35,
                "currency": "USD",
                "min_condition": "VG+",
                "is_active": True,
                "created_at": "2026-01-20T11:52:00+00:00",
                "updated_at": "2026-01-20T12:00:00+00:00",
            }
        },
    )

    id: UUID
    user_id: UUID
    discogs_release_id: int
    title: str
    artist: str | None
    year: int | None
    target_price: float | None
    currency: str
    min_condition: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
