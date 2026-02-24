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
        s_clean = str(s).strip().lower()
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
        return _normalize_and_validate_sources(v, require=True)


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
        return _normalize_and_validate_sources(v, require=False)


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
