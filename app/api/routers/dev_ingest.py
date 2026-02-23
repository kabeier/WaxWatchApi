from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.core.logging import get_logger
from app.schemas.ingest import IngestResult
from app.schemas.listings import ListingIngest, ListingOut
from app.services.ingest import ingest_and_match

logger = get_logger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/listings/ingest", response_model=IngestResult, status_code=200)
def ingest_listing(
    request: Request,
    payload: ListingIngest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")

    logger.info(
        "dev.ingest_listing.call",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "provider": getattr(payload, "provider", None),
            "external_id": getattr(payload, "external_id", None),
        },
    )

    try:
        listing, created_listing, created_snapshot, created_matches = ingest_and_match(
            db,
            user_id=user_id,
            listing_payload=payload.model_dump(),
        )
    except ValueError as e:
        logger.info(
            "dev.ingest_listing.validation_error",
            extra={"request_id": request_id, "user_id": str(user_id), "error": str(e)[:500]},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLAlchemyError:
        logger.exception(
            "dev.ingest_listing.db_error",
            extra={"request_id": request_id, "user_id": str(user_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "dev.ingest_listing.success",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "listing_id": str(getattr(listing, "id", "")),
            "created_listing": created_listing,
            "created_snapshot": created_snapshot,
            "created_matches": created_matches,
        },
    )

    return IngestResult(
        listing=ListingOut.model_validate(listing),
        created_listing=created_listing,
        created_snapshot=created_snapshot,
        created_matches=created_matches,
    )
