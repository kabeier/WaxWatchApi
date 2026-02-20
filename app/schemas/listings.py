from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ListingIngest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)  
    external_id: str = Field(min_length=1, max_length=120)

    url: str
    title: str
    price: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    condition: Optional[str] = None
    seller: Optional[str] = None
    location: Optional[str] = None
    discogs_release_id: Optional[int] = None

    raw: Optional[dict[str, Any]] = None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    external_id: str
    url: str
    title: str
    normalized_title: Optional[str]
    price: float
    currency: str
    condition: Optional[str]
    seller: Optional[str]
    location: Optional[str]
    status: str
    discogs_release_id: Optional[int]
    first_seen_at: datetime
    last_seen_at: datetime