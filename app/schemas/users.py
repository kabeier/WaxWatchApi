from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class IntegrationSummary(BaseModel):
    provider: str
    linked: bool = False
    watch_rule_count: int = 0


class UserPreferences(BaseModel):
    model_config = ConfigDict(extra="allow")

    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notifications_email: bool | None = None
    notifications_push: bool | None = None


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str | None = None
    is_active: bool
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    integrations: list[IntegrationSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    preferences: UserPreferences | None = None


class LogoutResponse(BaseModel):
    success: bool = True
    marker: dict[str, Any]


class DeactivateAccountResponse(BaseModel):
    success: bool = True
    deactivated_at: datetime
