from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db import models
from app.services.notifications import enqueue_from_event


def create_watch_release(
    db: Session,
    *,
    user_id: UUID,
    discogs_release_id: int,
    title: str,
    artist: str | None,
    year: int | None,
    target_price: float | None,
    currency: str,
    min_condition: str | None,
    is_active: bool,
) -> models.WatchRelease:
    now = datetime.now(timezone.utc)
    watch = models.WatchRelease(
        user_id=user_id,
        discogs_release_id=discogs_release_id,
        title=title,
        artist=artist,
        year=year,
        target_price=target_price,
        currency=currency.upper(),
        min_condition=min_condition,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(watch)
    db.flush()
    db.refresh(watch)

    _create_event(
        db,
        user_id=user_id,
        event_type=models.EventType.WATCH_RELEASE_CREATED,
        watch_release_id=watch.id,
    )
    return watch


def list_watch_releases(
    db: Session,
    *,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
    cursor_created_at: datetime | None = None,
    cursor_id: UUID | None = None,
) -> list[models.WatchRelease]:
    query = (
        db.query(models.WatchRelease)
        .filter(models.WatchRelease.user_id == user_id)
        .order_by(models.WatchRelease.created_at.desc(), models.WatchRelease.id.desc())
    )

    if cursor_created_at is not None and cursor_id is not None:
        query = query.filter(
            or_(
                models.WatchRelease.created_at < cursor_created_at,
                and_(
                    models.WatchRelease.created_at == cursor_created_at,
                    models.WatchRelease.id < cursor_id,
                ),
            )
        )
    elif offset:
        query = query.offset(offset)

    rows = query.limit(limit).all()
    return list(rows)


def get_watch_release(db: Session, *, user_id: UUID, watch_release_id: UUID) -> models.WatchRelease:
    row = (
        db.query(models.WatchRelease)
        .filter(models.WatchRelease.user_id == user_id)
        .filter(models.WatchRelease.id == watch_release_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Watch release not found")
    return row


def update_watch_release(
    db: Session,
    *,
    user_id: UUID,
    watch_release_id: UUID,
    discogs_release_id: int | None = None,
    title: str | None = None,
    artist: str | None = None,
    year: int | None = None,
    target_price: float | None = None,
    currency: str | None = None,
    min_condition: str | None = None,
    is_active: bool | None = None,
) -> models.WatchRelease:
    row = get_watch_release(db, user_id=user_id, watch_release_id=watch_release_id)

    changed = False
    active_changed: bool | None = None

    if discogs_release_id is not None and discogs_release_id != row.discogs_release_id:
        row.discogs_release_id = discogs_release_id
        changed = True
    if title is not None and title != row.title:
        row.title = title
        changed = True
    if artist is not None and artist != row.artist:
        row.artist = artist
        changed = True
    if year is not None and year != row.year:
        row.year = year
        changed = True
    if target_price is not None and target_price != row.target_price:
        row.target_price = target_price
        changed = True
    if currency is not None and currency.upper() != row.currency:
        row.currency = currency.upper()
        changed = True
    if min_condition is not None and min_condition != row.min_condition:
        row.min_condition = min_condition
        changed = True
    if is_active is not None and is_active != row.is_active:
        row.is_active = is_active
        changed = True
        active_changed = is_active

    if changed:
        row.updated_at = datetime.now(timezone.utc)
        _create_event(
            db,
            user_id=user_id,
            event_type=models.EventType.WATCH_RELEASE_UPDATED,
            watch_release_id=row.id,
        )
        if active_changed is True:
            _create_event(
                db,
                user_id=user_id,
                event_type=models.EventType.WATCH_RELEASE_ENABLED,
                watch_release_id=row.id,
            )
        elif active_changed is False:
            _create_event(
                db,
                user_id=user_id,
                event_type=models.EventType.WATCH_RELEASE_DISABLED,
                watch_release_id=row.id,
            )

    db.add(row)
    db.flush()
    db.refresh(row)
    return row


def disable_watch_release(db: Session, *, user_id: UUID, watch_release_id: UUID) -> models.WatchRelease:
    return update_watch_release(db, user_id=user_id, watch_release_id=watch_release_id, is_active=False)


def _create_event(
    db: Session,
    *,
    user_id: UUID,
    event_type: models.EventType,
    watch_release_id: UUID,
) -> models.Event:
    event = models.Event(
        user_id=user_id,
        type=event_type,
        watch_release_id=watch_release_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()
    enqueue_from_event(db, event=event)
    return event
