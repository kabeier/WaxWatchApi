from __future__ import annotations

from pydantic import BaseModel

from app.schemas.listings import ListingOut


class IngestResult(BaseModel):
    listing: ListingOut
    created_listing: bool
    created_snapshot: bool
    created_matches: int
