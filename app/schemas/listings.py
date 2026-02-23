from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.monetization.ebay_affiliate import to_affiliate_url


class ListingIngest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=120)

    url: str
    title: str
    price: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    condition: str | None = None
    seller: str | None = None
    location: str | None = None
    discogs_release_id: int | None = None

    raw: dict[str, Any] | None = None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    external_id: str
    url: str
    title: str
    normalized_title: str | None
    price: float
    currency: str
    condition: str | None
    seller: str | None
    location: str | None
    status: str
    discogs_release_id: int | None
    first_seen_at: datetime
    last_seen_at: datetime

    @computed_field(return_type=str)
    @property
    def public_url(self) -> str:
        if self.provider == "ebay":
            return to_affiliate_url(self.url)
        return self.url
