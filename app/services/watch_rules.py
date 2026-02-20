from __future__ import annotations

from datetime import datetime, UTC
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import models

from app.core.config import settings


def ensure_user_exists(db: Session, user_id: UUID) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        return user

    if not settings.dev_auto_create_users:
        raise HTTPException(status_code=401, detail="Unknown user")
    
    # dev  user - replace with real auth later
    user = models.User(
        id=user_id,
        email=f"dev+{user_id}@waxwatch.local",
        hashed_password="__dev_stub__",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def create_watch_rule(db: Session, *, user_id: UUID, name: str, query: dict, poll_interval_seconds: int) -> models.WatchSearchRule:
    ensure_user_exists(db, user_id)
    rule = models.WatchSearchRule(
        user_id=user_id,
        name=name,
        query=query,
        poll_interval_seconds=poll_interval_seconds,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # Optional: create an Event record for UI feed / websockets later
    _create_event(db, user_id=user_id, event_type=models.EventType.RULE_CREATED, rule_id=rule.id)

    return rule


def list_watch_rules(db: Session, *, user_id: UUID, limit: int = 50, offset: int = 0) -> list[models.WatchSearchRule]:
    q = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.user_id == user_id)
        .order_by(models.WatchSearchRule.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(q.all())


def get_watch_rule(db: Session, *, user_id: UUID, rule_id: UUID) -> models.WatchSearchRule:
    rule = (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.id == rule_id)
        .filter(models.WatchSearchRule.user_id == user_id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Watch rule not found")
    return rule


def update_watch_rule(
    db: Session,
    *,
    user_id: UUID,
    rule_id: UUID,
    name: str | None = None,
    query: dict | None = None,
    is_active: bool | None = None,
    poll_interval_seconds: int | None = None,
) -> models.WatchSearchRule:
    rule = get_watch_rule(db, user_id=user_id, rule_id=rule_id)

    changed = False
    if name is not None and name != rule.name:
        rule.name = name
        changed = True
    if query is not None and query != rule.query:
        rule.query = query
        changed = True
    if is_active is not None and is_active != rule.is_active:
        rule.is_active = is_active
        changed = True
    if poll_interval_seconds is not None and poll_interval_seconds != rule.poll_interval_seconds:
        rule.poll_interval_seconds = poll_interval_seconds
        changed = True

    if changed:
        rule.updated_at = datetime.now(UTC)
        db.add(rule)
        db.commit()
        db.refresh(rule)

        _create_event(db, user_id=user_id, event_type=models.EventType.RULE_UPDATED, rule_id=rule.id)

        if is_active is True:
            _create_event(db, user_id=user_id, event_type=models.EventType.RULE_ENABLED, rule_id=rule.id)
        elif is_active is False:
            _create_event(db, user_id=user_id, event_type=models.EventType.RULE_DISABLED, rule_id=rule.id)

    return rule


def disable_watch_rule(db: Session, *, user_id: UUID, rule_id: UUID) -> models.WatchSearchRule:
    # soft-delete = disable
    return update_watch_rule(db, user_id=user_id, rule_id=rule_id, is_active=False)


def _create_event(
    db: Session,
    *,
    user_id: UUID,
    event_type: models.EventType,
    rule_id: UUID | None = None,
) -> None:
    ev = models.Event(
        user_id=user_id,
        type=event_type,
        rule_id=rule_id,
        payload=None,
        created_at=datetime.now(UTC),
    )
    db.add(ev)
    db.commit()