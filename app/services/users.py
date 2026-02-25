from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import models
from app.schemas.users import IntegrationSummary, UserPreferences

DEFAULT_PROVIDER_SUMMARY = tuple(p.value for p in models.Provider)


def _preferences_from_claims_or_empty(token_claims: dict | None) -> dict:
    if not isinstance(token_claims, dict):
        return {}
    metadata = token_claims.get("user_metadata")
    if not isinstance(metadata, dict):
        return {}
    prefs = metadata.get("preferences")
    if not isinstance(prefs, dict):
        return {}
    return prefs


def get_user_profile(
    db: Session,
    *,
    user_id: UUID,
    token_claims: dict | None = None,
) -> dict:
    user = _owned_user(db, user_id=user_id)
    integrations = _integration_summary_for_user(db, user_id=user_id)

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "preferences": UserPreferences.model_validate(_preferences_from_claims_or_empty(token_claims)),
        "integrations": integrations,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def update_user_profile(
    db: Session,
    *,
    user_id: UUID,
    display_name: str | None = None,
    preferences: UserPreferences | None = None,
    token_claims: dict | None = None,
) -> dict:
    user = _owned_active_user(db, user_id=user_id)
    changed = False

    if display_name is not None and display_name != user.display_name:
        user.display_name = display_name
        changed = True

    if changed:
        user.updated_at = datetime.now(timezone.utc)
        db.add(user)
        db.flush()

    current_prefs = _preferences_from_claims_or_empty(token_claims)
    if preferences is not None:
        current_prefs.update(preferences.model_dump(exclude_none=True))

    profile = get_user_profile(
        db, user_id=user_id, token_claims={"user_metadata": {"preferences": current_prefs}}
    )
    profile["updated_at"] = user.updated_at
    return profile


def build_logout_marker(*, user_id: UUID) -> dict:
    return {
        "user_id": str(user_id),
        "logged_out_at": datetime.now(timezone.utc).isoformat(),
        "invalidate_before": datetime.now(timezone.utc).isoformat(),
    }


def deactivate_user_account(db: Session, *, user_id: UUID) -> datetime:
    user = _owned_active_user(db, user_id=user_id)

    now = datetime.now(timezone.utc)
    (
        db.query(models.WatchSearchRule)
        .filter(models.WatchSearchRule.user_id == user_id)
        .filter(models.WatchSearchRule.is_active.is_(True))
        .update(
            {
                models.WatchSearchRule.is_active: False,
                models.WatchSearchRule.updated_at: now,
            },
            synchronize_session=False,
        )
    )

    user.is_active = False
    user.updated_at = now
    db.add(user)
    db.flush()
    return user.updated_at


def hard_delete_user_account(db: Session, *, user_id: UUID) -> datetime:
    user = _owned_user(db, user_id=user_id)
    deleted_at = datetime.now(timezone.utc)
    db.delete(user)
    db.flush()
    return deleted_at


def _owned_user(db: Session, *, user_id: UUID) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User profile not found")
    return user


def _owned_active_user(db: Session, *, user_id: UUID) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User profile not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return user


def _integration_summary_for_user(db: Session, *, user_id: UUID) -> list[IntegrationSummary]:
    counts: dict[str, int] = {provider: 0 for provider in DEFAULT_PROVIDER_SUMMARY}
    rules = db.query(models.WatchSearchRule.query).filter(models.WatchSearchRule.user_id == user_id).all()
    for (query_payload,) in rules:
        if not isinstance(query_payload, dict):
            continue
        sources = query_payload.get("sources")
        if not isinstance(sources, list):
            continue
        for source in sources:
            key = str(source).strip().lower()
            if key in counts:
                counts[key] += 1

    return [
        IntegrationSummary(provider=provider, linked=counts[provider] > 0, watch_rule_count=counts[provider])
        for provider in DEFAULT_PROVIDER_SUMMARY
    ]
