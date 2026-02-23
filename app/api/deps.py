from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth import build_verifier
from app.db.base import SessionLocal


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


bearer_scheme = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _get_auth_verifier():
    return build_verifier()


def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> UUID:
    verified = _get_auth_verifier().verify(credentials.credentials)
    request.state.user_id = str(verified.user_id)
    request.state.token_claims = verified.claims
    return verified.user_id
