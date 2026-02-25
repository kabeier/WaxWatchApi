from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import models
from app.providers.registry import list_available_providers
from app.schemas.users import IntegrationSummary, UserPreferences
from app.services.notifications import get_or_create_preferences

DEFAULT_PROVIDER_SUMMARY = tuple(list_available_providers())


def _preferences_from_db(
    user: models.User,
    notification_preferences: models.UserNotificationPreference,
) -> UserPreferences:
    return UserPreferences(
        timezone=user.timezone,
        currency=user.currency,
        notifications_email=notification_preferences.email_enabled,
        notifications_push=notification_preferences.realtime_enabled,
        quiet_hours_start=notification_preferences.quiet_hours_start,
        quiet_hours_end=notification_preferences.quiet_hours_end,
        notification_timezone=notification_preferences.timezone_override,
        delivery_frequency=notification_preferences.delivery_frequency,
    )


def get_user_profile(
    db: Session,
    *,
    user_id: UUID,
    token_claims: dict | None = None,
) -> dict:
    _ = token_claims
    user = _owned_user(db, user_id=user_id)
    notification_preferences = get_or_create_preferences(db, user_id=user_id)
    integrations = _integration_summary_for_user(db, user_id=user_id)

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "preferences": _preferences_from_db(user, notification_preferences),
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
    _ = token_claims
    user = _owned_active_user(db, user_id=user_id)
    notification_preferences = get_or_create_preferences(db, user_id=user_id)
    changed = False

    if display_name is not None and display_name != user.display_name:
        user.display_name = display_name
        changed = True

    if preferences is not None:
        if preferences.timezone is not None and preferences.timezone != user.timezone:
            user.timezone = preferences.timezone
            changed = True
        if preferences.currency is not None and preferences.currency != user.currency:
            user.currency = preferences.currency
            changed = True
        if (
            preferences.notifications_email is not None
            and preferences.notifications_email != notification_preferences.email_enabled
        ):
            notification_preferences.email_enabled = preferences.notifications_email
            changed = True
        if (
            preferences.notifications_push is not None
            and preferences.notifications_push != notification_preferences.realtime_enabled
        ):
            notification_preferences.realtime_enabled = preferences.notifications_push
            changed = True
        if (
            preferences.quiet_hours_start is not None
            and preferences.quiet_hours_start != notification_preferences.quiet_hours_start
        ):
            notification_preferences.quiet_hours_start = preferences.quiet_hours_start
            changed = True
        if (
            preferences.quiet_hours_end is not None
            and preferences.quiet_hours_end != notification_preferences.quiet_hours_end
        ):
            notification_preferences.quiet_hours_end = preferences.quiet_hours_end
            changed = True
        if (
            preferences.notification_timezone is not None
            and preferences.notification_timezone != notification_preferences.timezone_override
        ):
            notification_preferences.timezone_override = preferences.notification_timezone
            changed = True
        if (
            preferences.delivery_frequency is not None
            and preferences.delivery_frequency != notification_preferences.delivery_frequency
        ):
            notification_preferences.delivery_frequency = preferences.delivery_frequency
            changed = True

    if changed:
        now = datetime.now(timezone.utc)
        user.updated_at = now
        notification_preferences.updated_at = now
        db.add(user)
        db.add(notification_preferences)
        db.flush()

    profile = get_user_profile(db, user_id=user_id)
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
    linked_by_provider: dict[str, bool] = {provider: False for provider in DEFAULT_PROVIDER_SUMMARY}

    links = (
        db.query(models.ExternalAccountLink.provider)
        .filter(models.ExternalAccountLink.user_id == user_id)
        .all()
    )
    for (provider,) in links:
        provider_key = provider.value if isinstance(provider, models.Provider) else str(provider)
        key = provider_key.strip().lower()
        if key in linked_by_provider:
            linked_by_provider[key] = True

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
        IntegrationSummary(
            provider=provider,
            linked=linked_by_provider[provider],
            watch_rule_count=counts[provider],
        )
        for provider in DEFAULT_PROVIDER_SUMMARY
    ]
