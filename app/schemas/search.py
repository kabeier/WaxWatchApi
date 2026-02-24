from __future__ import annotations

import math

from pydantic import BaseModel, Field, computed_field, field_validator

from app.db import models
from app.monetization.ebay_affiliate import to_affiliate_url
from app.providers.registry import PROVIDERS


class SearchQuery(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    providers: list[str] | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_condition: str | None = Field(default=None, min_length=1, max_length=30)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=24, ge=1, le=100)

    @field_validator("providers")
    @classmethod
    def validate_providers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned: list[str] = []
        for provider in value:
            key = str(provider).strip().lower()
            if not key:
                continue
            try:
                models.Provider(key)
            except ValueError as exc:
                raise ValueError(f"Invalid provider: {key}") from exc
            if key not in PROVIDERS:
                raise ValueError(f"Unsupported provider: {key}")
            cleaned.append(key)

        if not cleaned:
            raise ValueError("providers must contain at least one valid provider")

        return list(dict.fromkeys(cleaned))

    @field_validator("max_price")
    @classmethod
    def validate_price_range(cls, value: float | None, info):
        min_price = info.data.get("min_price")
        if value is not None and min_price is not None and value < min_price:
            raise ValueError("max_price must be greater than or equal to min_price")
        return value


class SearchListingOut(BaseModel):
    id: str
    provider: str
    external_id: str
    title: str
    url: str
    price: float
    currency: str
    condition: str | None
    seller: str | None
    location: str | None
    discogs_release_id: int | None

    @computed_field(return_type=str)
    @property
    def public_url(self) -> str:
        if self.provider == "ebay":
            return to_affiliate_url(self.url)
        return self.url


class SearchPagination(BaseModel):
    page: int
    page_size: int
    total: int
    returned: int
    total_pages: int
    has_next: bool

    @classmethod
    def build(cls, *, page: int, page_size: int, total: int, returned: int) -> SearchPagination:
        total_pages = math.ceil(total / page_size) if total else 0
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            returned=returned,
            total_pages=total_pages,
            has_next=page < total_pages,
        )


class SearchResponse(BaseModel):
    items: list[SearchListingOut]
    pagination: SearchPagination
    providers_searched: list[str]
    provider_errors: dict[str, str] = Field(default_factory=dict)


class SaveSearchAlertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: SearchQuery
    poll_interval_seconds: int = Field(default=600, ge=30, le=24 * 60 * 60)
