from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db, rate_limit_scope
from app.core.logging import redact_sensitive_data
from app.schemas.discogs import (
    DiscogsConnectIn,
    DiscogsConnectOut,
    DiscogsDisconnectIn,
    DiscogsDisconnectOut,
    DiscogsImportedItemListOut,
    DiscogsImportIn,
    DiscogsImportJobOut,
    DiscogsOAuthCallbackIn,
    DiscogsOAuthStartIn,
    DiscogsOAuthStartOut,
    DiscogsOpenInDiscogsOut,
    DiscogsStatusOut,
)
from app.services.discogs_import import discogs_import_service
from app.tasks import run_discogs_import_task

router = APIRouter(
    prefix="/integrations/discogs",
    tags=["integrations", "discogs"],
    dependencies=[Depends(rate_limit_scope("discogs", require_authenticated_principal=True))],
)


@router.post(
    "/oauth/start",
    response_model=DiscogsOAuthStartOut,
    dependencies=[Depends(rate_limit_scope("auth_endpoints"))],
)
def start_discogs_oauth(
    payload: DiscogsOAuthStartIn,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    started = discogs_import_service.start_oauth(db, user_id=user_id, scopes=payload.scopes)
    return DiscogsOAuthStartOut(**started)


@router.post(
    "/oauth/callback",
    response_model=DiscogsConnectOut,
    dependencies=[Depends(rate_limit_scope("auth_endpoints"))],
)
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
    job, created = discogs_import_service.ensure_import_job(db, user_id=user_id, source=payload.source)
    # Ensure the queued task can always read the job row.
    # In eager mode this avoids `Import job not found` when task execution happens
    # before dependency teardown commits the transaction.
    db.commit()
    if not created:
        db.refresh(job)
        return job

    try:
        run_discogs_import_task.delay(str(job.id))
    except Exception as exc:
        now = datetime.now(timezone.utc)
        job.status = "failed_to_queue"
        job.error_count += 1
        safe_error = str(redact_sensitive_data(str(exc)))
        job.errors = [*(job.errors or []), {"error": "queue_dispatch_failed", "detail": safe_error}]
        job.completed_at = now
        job.updated_at = now

        db.add(job)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Discogs import could not be queued. Please retry shortly.",
        ) from exc

    db.refresh(job)
    return job


@router.get("/import/{job_id}", response_model=DiscogsImportJobOut)
def get_import_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return discogs_import_service.get_job(db, user_id=user_id, job_id=job_id)


@router.get("/imported-items", response_model=DiscogsImportedItemListOut)
def list_imported_discogs_items(
    source: Literal["wantlist", "collection"] = Query(...),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return discogs_import_service.list_imported_items(
        db,
        user_id=user_id,
        source=source,
        limit=limit,
        offset=offset,
    )


@router.get("/imported-items/{watch_release_id}/open-in-discogs", response_model=DiscogsOpenInDiscogsOut)
def open_imported_item_in_discogs(
    watch_release_id: UUID,
    source: Literal["wantlist", "collection"] = Query(...),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return discogs_import_service.get_open_in_discogs_link(
        db,
        user_id=user_id,
        watch_release_id=watch_release_id,
        source=source,
    )
