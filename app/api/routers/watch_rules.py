from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.watch_rules import WatchRuleCreate, WatchRuleOut, WatchRuleUpdate
from app.services import watch_rules as service
from app.services.background import backfill_rule_matches_task
from fastapi import BackgroundTasks


router = APIRouter(prefix="/watch-rules", tags=["watch-rules"])


def get_current_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> UUID:
    # Temporary auth stub:
    # You pass a UUID in header X-User-Id.
    # Replace this with JWT later.
    return UUID(x_user_id)


@router.post("", response_model=WatchRuleOut, status_code=201)
def create_rule(
    payload: WatchRuleCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return service.create_watch_rule(
        db,
        user_id=user_id,
        name=payload.name,
        query=payload.query,
        poll_interval_seconds=payload.poll_interval_seconds,
    )


@router.get("", response_model=list[WatchRuleOut])
def list_rules(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.list_watch_rules(db, user_id=user_id, limit=limit, offset=offset)


@router.get("/{rule_id}", response_model=WatchRuleOut)
def get_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return service.get_watch_rule(db, user_id=user_id, rule_id=rule_id)


@router.patch("/{rule_id}", response_model=WatchRuleOut)
def patch_rule(
    rule_id: UUID,
    payload: WatchRuleUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return service.update_watch_rule(
        db,
        user_id=user_id,
        rule_id=rule_id,
        name=payload.name,
        query=payload.query,
        is_active=payload.is_active,
        poll_interval_seconds=payload.poll_interval_seconds,
    )


@router.delete("/{rule_id}", response_model=WatchRuleOut)
def disable_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return service.disable_watch_rule(db, user_id=user_id, rule_id=rule_id)