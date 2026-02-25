from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.notifications import DeliveryFrequency


class IntegrationSummary(BaseModel):
    provider: str
    linked: bool = False
    watch_rule_count: int = 0


class UserPreferences(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "timezone": "America/New_York",
                "currency": "USD",
                "notifications_email": True,
                "notifications_push": True,
                "quiet_hours_start": 22,
                "quiet_hours_end": 7,
                "notification_timezone": "America/Los_Angeles",
                "delivery_frequency": "hourly",
            }
        },
    )

    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notifications_email: bool | None = None
    notifications_push: bool | None = None
    quiet_hours_start: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end: int | None = Field(default=None, ge=0, le=23)
    notification_timezone: str | None = Field(default=None, max_length=64)
    delivery_frequency: DeliveryFrequency | None = None


class UserProfileOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "8f2a5009-c0a2-4f90-8f1b-c1716c26bf06",
                "email": "collector@example.com",
                "display_name": "Wax Hunter",
                "is_active": True,
                "preferences": {
                    "timezone": "America/New_York",
                    "currency": "USD",
                    "notifications_email": True,
                    "notifications_push": True,
                    "quiet_hours_start": 22,
                    "quiet_hours_end": 7,
                    "notification_timezone": "America/Los_Angeles",
                    "delivery_frequency": "hourly",
                },
                "integrations": [{"provider": "discogs", "linked": True, "watch_rule_count": 4}],
                "created_at": "2026-01-10T15:34:12.123456+00:00",
                "updated_at": "2026-01-20T09:10:44.987654+00:00",
            }
        },
    )

    id: UUID
    email: EmailStr
    display_name: str | None = None
    is_active: bool
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    integrations: list[IntegrationSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "Wax Hunter",
                "preferences": {
                    "timezone": "America/Chicago",
                    "currency": "USD",
                    "notifications_email": True,
                    "notifications_push": False,
                    "quiet_hours_start": 23,
                    "quiet_hours_end": 6,
                    "notification_timezone": "America/Chicago",
                    "delivery_frequency": "daily",
                },
            }
        }
    )

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    preferences: UserPreferences | None = None


class LogoutResponse(BaseModel):
    success: bool = True
    marker: dict[str, Any]


class DeactivateAccountResponse(BaseModel):
    success: bool = True
    deactivated_at: datetime


class HardDeleteAccountResponse(BaseModel):
    success: bool = True
    deleted_at: datetime
