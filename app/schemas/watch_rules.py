from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db import models


def _normalize_and_validate_sources(query: dict[str, Any], *, require: bool) -> dict[str, Any]:
    sources = query.get("sources", None)

    if sources is None:
        if require:
            raise ValueError("query.sources is required and must be a non-empty list")
        return query  # nothing to validate

    if not isinstance(sources, list) or not sources:
        raise ValueError("query.sources must be a non-empty list")

    cleaned: list[str] = []
    for s in sources:
        if not isinstance(s, str):
            raise ValueError("query.sources entries must be strings")

        s_clean = s.strip().lower()
        if not s_clean:
            continue
        try:
            models.Provider(s_clean)
        except ValueError as e:
            raise ValueError(f"Invalid provider source: {s_clean}") from e
        cleaned.append(s_clean)

    if not cleaned:
        raise ValueError("query.sources must contain at least one valid provider")

    query["sources"] = list(dict.fromkeys(cleaned))  # dedupe, preserve order
    return query


def _normalize_and_validate_keywords(
    query: dict[str, Any], *, require_non_empty_when_present: bool
) -> dict[str, Any]:
    keywords = query.get("keywords", None)

    if keywords is None:
        return query

    if not isinstance(keywords, list):
        raise ValueError("query.keywords must be a list when provided")

    cleaned: list[str] = []
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ValueError("query.keywords entries must be strings")
        normalized = keyword.strip().lower()
        if normalized:
            cleaned.append(normalized)

    if require_non_empty_when_present and keywords and not cleaned:
        raise ValueError("query.keywords must contain at least one non-empty keyword when provided")

    query["keywords"] = cleaned
    return query


def _normalize_and_validate_known_keys(
    query: dict[str, Any], *, allow_null_known_keys: bool
) -> dict[str, Any]:
    q_value = query.get("q")
    if q_value is not None:
        if not isinstance(q_value, str):
            raise ValueError("query.q must be a string when provided")
        normalized_q = q_value.strip().lower()
        if not normalized_q:
            raise ValueError("query.q must be non-empty when provided")
        query["q"] = normalized_q
    elif "q" in query and not allow_null_known_keys:
        raise ValueError("query.q must be a string when provided")

    max_price = query.get("max_price")
    if max_price is not None:
        if not isinstance(max_price, (int, float)) or isinstance(max_price, bool):
            raise ValueError("query.max_price must be a numeric value")
        if max_price < 0:
            raise ValueError("query.max_price must be non-negative")
        query["max_price"] = float(max_price)
    elif "max_price" in query and not allow_null_known_keys:
        raise ValueError("query.max_price must be a numeric value")

    return query


class WatchRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: dict[str, Any] = Field(default_factory=dict)

    is_active: bool = True
    poll_interval_seconds: int = Field(default=600, ge=30, le=24 * 60 * 60)


class WatchRuleCreate(WatchRuleBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Rare techno under $40",
                "query": {"q": "detroit techno", "max_price": 40, "sources": ["discogs"]},
                "is_active": True,
                "poll_interval_seconds": 600,
            }
        }
    )

    @field_validator("query")
    @classmethod
    def require_sources_on_create(cls, v: dict[str, Any]) -> dict[str, Any]:
        v = _normalize_and_validate_known_keys(v, allow_null_known_keys=False)
        v = _normalize_and_validate_sources(v, require=True)
        return _normalize_and_validate_keywords(v, require_non_empty_when_present=True)


class WatchRuleUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Rare techno under $30",
                "query": {"q": "detroit techno", "max_price": 30, "sources": ["discogs"]},
                "is_active": True,
                "poll_interval_seconds": 900,
            }
        }
    )

    # PATCH: all optional
    name: str | None = Field(default=None, min_length=1, max_length=120)
    query: dict[str, Any] | None = None
    is_active: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=30, le=24 * 60 * 60)

    @field_validator("query")
    @classmethod
    def validate_sources_if_present(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        v = _normalize_and_validate_known_keys(v, allow_null_known_keys=True)
        v = _normalize_and_validate_sources(v, require=False)
        return _normalize_and_validate_keywords(v, require_non_empty_when_present=True)


class WatchRuleOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "80dc6333-3c3c-49b8-a803-938783fbeb99",
                "user_id": "8f2a5009-c0a2-4f90-8f1b-c1716c26bf06",
                "name": "Rare techno under $40",
                "query": {"q": "detroit techno", "max_price": 40, "sources": ["discogs"]},
                "is_active": True,
                "poll_interval_seconds": 600,
                "last_run_at": "2026-01-20T12:00:00+00:00",
                "next_run_at": "2026-01-20T12:10:00+00:00",
                "created_at": "2026-01-20T11:52:00+00:00",
                "updated_at": "2026-01-20T12:00:00+00:00",
            }
        },
    )

    id: UUID
    user_id: UUID

    name: str
    query: dict[str, Any]
    is_active: bool
    poll_interval_seconds: int

    last_run_at: datetime | None
    next_run_at: datetime | None

    created_at: datetime
    updated_at: datetime
