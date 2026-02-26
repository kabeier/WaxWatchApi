from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth import build_verifier
from app.core.logging import get_logger
from app.core.rate_limit import ScopeName, enforce_rate_limit
from app.db import models
from app.db.base import SessionLocal

logger = get_logger("app.auth")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except:
        db.rollback()
        raise
    finally:
        db.close()


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_auth_verifier():
    return build_verifier()


def _resolve_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    *,
    require_active: bool,
) -> UUID:
    if credentials is None:
        logger.info(
            "auth.missing_bearer",
            extra={
                "request_id": getattr(request.state, "request_id", "-"),
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    verified = _get_auth_verifier().verify(credentials.credentials)

    user = db.query(models.User).filter(models.User.id == verified.user_id).first()
    if require_active and user is not None and not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    request.state.user_id = str(verified.user_id)
    request.state.token_claims = verified.claims
    return verified.user_id


def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> UUID:
    return _resolve_current_user(request, credentials, db, require_active=True)


def get_current_user_id_allow_inactive(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> UUID:
    return _resolve_current_user(request, credentials, db, require_active=False)


def _has_admin_claims(claims: dict | None) -> bool:
    if not isinstance(claims, dict):
        return False

    admin_roles = {"admin", "service_role"}
    direct_role_claims = (claims.get("role"), claims.get("user_role"))
    for role in direct_role_claims:
        if isinstance(role, str) and role.strip().lower() in admin_roles:
            return True

    app_metadata = claims.get("app_metadata")
    if isinstance(app_metadata, dict):
        app_role = app_metadata.get("role")
        if isinstance(app_role, str) and app_role.strip().lower() in admin_roles:
            return True
        app_roles = app_metadata.get("roles")
        if isinstance(app_roles, list) and any(
            isinstance(role, str) and role.strip().lower() in admin_roles for role in app_roles
        ):
            return True

    raw_scope = claims.get("scope")
    scopes = raw_scope.split() if isinstance(raw_scope, str) else []

    permission_like_claims = []
    for key in ("roles", "permissions"):
        value = claims.get(key)
        if isinstance(value, list):
            permission_like_claims.extend([v for v in value if isinstance(v, str)])

    normalized = {value.strip().lower() for value in [*scopes, *permission_like_claims]}
    return "provider_requests:read_all" in normalized or "admin" in normalized


def get_current_admin_user_id(
    request: Request,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> UUID:
    if not _has_admin_claims(getattr(request.state, "token_claims", None)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user_id


def rate_limit_scope(scope: ScopeName, *, require_authenticated_principal: bool = False):
    def _dependency(request: Request) -> None:
        enforce_rate_limit(
            request,
            scope=scope,
            require_authenticated_principal=require_authenticated_principal,
        )

    return _dependency
