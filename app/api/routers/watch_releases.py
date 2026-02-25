from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.api.pagination import PaginationParams, get_pagination_params
from app.schemas.watch_releases import WatchReleaseCreate, WatchReleaseOut, WatchReleaseUpdate
from app.services import watch_releases as service

router = APIRouter(prefix="/watch-releases", tags=["watch-releases"])


@router.post("", response_model=WatchReleaseOut, status_code=201)
def create_watch_release(
    payload: WatchReleaseCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return service.create_watch_release(
            db,
            user_id=user_id,
            discogs_release_id=payload.discogs_release_id,
            discogs_master_id=payload.discogs_master_id,
            match_mode=payload.match_mode,
            title=payload.title,
            artist=payload.artist,
            year=payload.year,
            target_price=payload.target_price,
            currency=payload.currency,
            min_condition=payload.min_condition,
            is_active=payload.is_active,
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="db error") from None


@router.get("", response_model=list[WatchReleaseOut])
def list_watch_releases(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    try:
        return service.list_watch_releases(
            db,
            user_id=user_id,
            limit=pagination.limit,
            offset=pagination.offset,
            cursor_created_at=pagination.cursor_created_at,
            cursor_id=pagination.cursor_id,
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="db error") from None


@router.get("/{watch_release_id}", response_model=WatchReleaseOut)
def get_watch_release(
    watch_release_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return service.get_watch_release(db, user_id=user_id, watch_release_id=watch_release_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="db error") from None


@router.patch("/{watch_release_id}", response_model=WatchReleaseOut)
def update_watch_release(
    watch_release_id: UUID,
    payload: WatchReleaseUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return service.update_watch_release(
            db,
            user_id=user_id,
            watch_release_id=watch_release_id,
            discogs_release_id=payload.discogs_release_id,
            discogs_master_id=payload.discogs_master_id,
            match_mode=payload.match_mode,
            title=payload.title,
            artist=payload.artist,
            year=payload.year,
            target_price=payload.target_price,
            currency=payload.currency,
            min_condition=payload.min_condition,
            is_active=payload.is_active,
        )
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="db error") from None


@router.delete("/{watch_release_id}", response_model=WatchReleaseOut)
def disable_watch_release(
    watch_release_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return service.disable_watch_release(db, user_id=user_id, watch_release_id=watch_release_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="db error") from None
