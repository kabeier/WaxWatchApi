from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: str

    watch_release_id: UUID | None
    rule_id: UUID | None
    listing_id: UUID | None

    payload: dict[str, Any] | None
    created_at: datetime
