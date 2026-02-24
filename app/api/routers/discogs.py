from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.discogs import (
    DiscogsConnectIn,
    DiscogsConnectOut,
    DiscogsImportIn,
    DiscogsImportJobOut,
    DiscogsStatusOut,
)
from app.services.discogs_import import discogs_import_service

router = APIRouter(prefix="/integrations/discogs", tags=["integrations", "discogs"])


@router.post("/connect", response_model=DiscogsConnectOut)
def connect_discogs(
    payload: DiscogsConnectIn,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    link = discogs_import_service.connect_account(
        db,
        user_id=user_id,
        external_user_id=payload.external_user_id,
        access_token=payload.access_token,
        token_metadata=payload.token_metadata,
    )
    return DiscogsConnectOut(
        provider=link.provider.value,
        external_user_id=link.external_user_id,
        connected=True,
        connected_at=link.connected_at,
    )


@router.get("/status", response_model=DiscogsStatusOut)
def discogs_status(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    link = discogs_import_service.get_status(db, user_id=user_id)
    if not link:
        return DiscogsStatusOut(connected=False, provider="discogs")

    return DiscogsStatusOut(
        connected=True,
        provider=link.provider.value,
        external_user_id=link.external_user_id,
        connected_at=link.connected_at,
        has_access_token=bool(link.access_token),
    )


@router.post("/import", response_model=DiscogsImportJobOut)
def import_discogs(
    payload: DiscogsImportIn,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return discogs_import_service.run_import(db, user_id=user_id, source=payload.source)


@router.get("/import/{job_id}", response_model=DiscogsImportJobOut)
def get_import_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return discogs_import_service.get_job(db, user_id=user_id, job_id=job_id)
