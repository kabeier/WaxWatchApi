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


def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
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
    if user is not None and not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    request.state.user_id = str(verified.user_id)
    request.state.token_claims = verified.claims
    return verified.user_id
