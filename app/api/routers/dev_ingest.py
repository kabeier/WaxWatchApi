from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.ingest import IngestResult
from app.schemas.listings import ListingIngest, ListingOut
from app.services.ingest import ingest_and_match

router = APIRouter(prefix="/dev", tags=["dev"])


def get_current_user_id(x_user_id: UUID = Header(..., alias="X-User-Id")) -> UUID:
    return x_user_id


@router.post("/listings/ingest", response_model=IngestResult, status_code=200)
def ingest_listing(
    payload: ListingIngest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    listing, created_listing, created_snapshot, created_matches = ingest_and_match(
        db,
        user_id=user_id,
        listing_payload=payload.model_dump(),
    )

    return IngestResult(
        listing=ListingOut.model_validate(listing),
        created_listing=created_listing,
        created_snapshot=created_snapshot,
        created_matches=created_matches,
    )