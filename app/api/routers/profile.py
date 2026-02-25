from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_current_user_id_allow_inactive, get_db
from app.core.logging import get_logger
from app.schemas.users import (
    DeactivateAccountResponse,
    HardDeleteAccountResponse,
    LogoutResponse,
    UserProfileOut,
    UserProfileUpdate,
)
from app.services import users as users_service

logger = get_logger(__name__)
router = APIRouter(prefix="/me", tags=["profile"])


@router.get("", response_model=UserProfileOut)
def get_me(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    claims = getattr(request.state, "token_claims", None)
    logger.debug("profile.get.call", extra={"request_id": request_id, "user_id": str(user_id)})
    return users_service.get_user_profile(db, user_id=user_id, token_claims=claims)


@router.patch("", response_model=UserProfileOut)
def patch_me(
    payload: UserProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    claims = getattr(request.state, "token_claims", None)
    logger.info(
        "profile.patch.call",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "has_display_name": payload.display_name is not None,
            "has_preferences": payload.preferences is not None,
        },
    )

    return users_service.update_user_profile(
        db,
        user_id=user_id,
        display_name=payload.display_name,
        preferences=payload.preferences,
        token_claims=claims,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout_me(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.info("profile.logout.call", extra={"request_id": request_id, "user_id": str(user_id)})
    marker = users_service.build_logout_marker(user_id=user_id)
    return LogoutResponse(marker=marker)


@router.delete("", response_model=DeactivateAccountResponse)
def deactivate_me(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.info("profile.deactivate.call", extra={"request_id": request_id, "user_id": str(user_id)})
    deactivated_at = users_service.deactivate_user_account(db, user_id=user_id)
    return DeactivateAccountResponse(deactivated_at=deactivated_at)


@router.delete("/hard-delete", response_model=HardDeleteAccountResponse)
def hard_delete_me(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id_allow_inactive),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.info("profile.hard_delete.call", extra={"request_id": request_id, "user_id": str(user_id)})
    deleted_at = users_service.hard_delete_user_account(db, user_id=user_id)
    return HardDeleteAccountResponse(deleted_at=deleted_at)
