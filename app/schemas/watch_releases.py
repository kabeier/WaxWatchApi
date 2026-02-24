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
    pass


class WatchReleaseUpdate(BaseModel):
    discogs_release_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    artist: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=0, le=9999)
    target_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    min_condition: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None


class WatchReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
