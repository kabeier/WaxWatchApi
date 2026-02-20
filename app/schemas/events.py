from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: str

    watch_release_id: Optional[UUID]
    rule_id: Optional[UUID]
    listing_id: Optional[UUID]

    payload: Optional[dict[str, Any]]
    created_at: datetime