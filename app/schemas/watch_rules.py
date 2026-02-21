from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.db import models



class WatchRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: dict[str, Any] = Field(default_factory=dict)

    is_active: bool = True
    poll_interval_seconds: int = Field(default=600, ge=30, le=24 * 60 * 60)


class WatchRuleCreate(WatchRuleBase):
    @field_validator("query")
    @classmethod
    def require_and_normalize_sources(cls, v: dict[str, Any]) -> dict[str, Any]:
        sources = v.get("sources")

        if not isinstance(sources, list) or not sources:
            raise ValueError("query.sources is required and must be a non-empty list")

        cleaned: list[str] = []
        for s in sources:
            s_clean = str(s).strip().lower()
            if not s_clean:
                continue
            # validate against enum
            try:
                models.Provider(s_clean)
            except ValueError:
                raise ValueError(f"Invalid provider source: {s_clean}")
            cleaned.append(s_clean)

        if not cleaned:
            raise ValueError("query.sources is required and must contain at least one valid provider")

        # dedupe, keep order
        v["sources"] = list(dict.fromkeys(cleaned))
        return v

class WatchRuleUpdate(BaseModel):
    # PATCH: all optional
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    query: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    poll_interval_seconds: Optional[int] = Field(default=None, ge=30, le=24 * 60 * 60)


class WatchRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID

    name: str
    query: dict[str, Any]
    is_active: bool
    poll_interval_seconds: int

    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]

    created_at: datetime
    updated_at: datetime