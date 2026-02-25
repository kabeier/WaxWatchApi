from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.discogs import (
    DiscogsConnectIn,
    DiscogsConnectOut,
    DiscogsDisconnectIn,
    DiscogsDisconnectOut,
    DiscogsImportIn,
    DiscogsImportJobOut,
    DiscogsOAuthCallbackIn,
    DiscogsOAuthStartIn,
    DiscogsOAuthStartOut,
    DiscogsStatusOut,
)
from app.services.discogs_import import discogs_import_service
from app.tasks import run_discogs_import_task

router = APIRouter(prefix="/integrations/discogs", tags=["integrations", "discogs"])


@router.post("/oauth/start", response_model=DiscogsOAuthStartOut)
def start_discogs_oauth(
    payload: DiscogsOAuthStartIn,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    started = discogs_import_service.start_oauth(db, user_id=user_id, scopes=payload.scopes)
    return DiscogsOAuthStartOut(**started)


@router.post("/oauth/callback", response_model=DiscogsConnectOut)
def complete_discogs_oauth(
    payload: DiscogsOAuthCallbackIn,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    link = discogs_import_service.complete_oauth(
        db,
        user_id=user_id,
        state=payload.state,
        code=payload.code,
    )
    return DiscogsConnectOut(
        provider=link.provider.value,
        external_user_id=link.external_user_id,
        connected=True,
        connected_at=link.connected_at,
    )


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


@router.post("/disconnect", response_model=DiscogsDisconnectOut)
def disconnect_discogs(
    payload: DiscogsDisconnectIn,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    disconnected = discogs_import_service.disconnect_account(
        db,
        user_id=user_id,
        revoke=payload.revoke,
    )
    return DiscogsDisconnectOut(provider="discogs", disconnected=disconnected)


@router.get("/status", response_model=DiscogsStatusOut)
def discogs_status(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    link = discogs_import_service.get_status(db, user_id=user_id)
    if not link:
        return DiscogsStatusOut(connected=False, provider="discogs")

    connected = bool(link.access_token and link.external_user_id != "pending")
    return DiscogsStatusOut(
        connected=connected,
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
    job = discogs_import_service.run_import(db, user_id=user_id, source=payload.source)
    run_discogs_import_task.delay(str(job.id))
    db.refresh(job)
    return job


@router.get("/import/{job_id}", response_model=DiscogsImportJobOut)
def get_import_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return discogs_import_service.get_job(db, user_id=user_id, job_id=job_id)
