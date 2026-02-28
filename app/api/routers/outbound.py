from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.db import models
from app.monetization.ebay_affiliate import to_affiliate_url

router = APIRouter(prefix="/outbound", tags=["outbound"])


@router.get("/ebay/{listing_id}", status_code=307)
def redirect_ebay_outbound(
    listing_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    referer: str | None = Header(default=None),
):
    try:
        listing = db.get(models.Listing, listing_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="db error") from exc
    if listing is None or listing.provider != models.Provider.ebay:
        raise HTTPException(status_code=404, detail="listing not found")

    destination = to_affiliate_url(listing.url)
    if not destination:
        raise HTTPException(status_code=404, detail="listing destination unavailable")

    try:
        db.add(
            models.OutboundClick(
                user_id=user_id,
                listing_id=listing.id,
                provider=listing.provider,
                referrer=referer,
            )
        )
        db.flush()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="db error") from exc

    return RedirectResponse(url=destination, status_code=307)
