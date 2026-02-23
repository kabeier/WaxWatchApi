from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError, PyJWK

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.auth")


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    claims: dict[str, Any]


class SupabaseJWTVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        algorithms: tuple[str, ...],
        jwks_cache_ttl_seconds: int,
        clock_skew_seconds: int,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self.algorithms = algorithms
        self.jwks_cache_ttl_seconds = jwks_cache_ttl_seconds
        self.clock_skew_seconds = clock_skew_seconds

        self._jwks: dict[str, Any] | None = None
        self._jwks_loaded_at: float = 0.0

    def _fetch_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks and (now - self._jwks_loaded_at) < self.jwks_cache_ttl_seconds:
            return self._jwks

        logger.info("auth.jwks.fetch", extra={"jwks_url": self.jwks_url})
        response = httpx.get(self.jwks_url, timeout=5.0)
        response.raise_for_status()
        try:
            jwks = response.json()
        except ValueError as exc:
            logger.info("auth.jwks.invalid_json")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="invalid jwks response",
            ) from exc
        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="invalid jwks response"
            )

        self._jwks = jwks
        self._jwks_loaded_at = now
        logger.info("auth.jwks.fetch.success", extra={"keys_count": len(jwks.get("keys", []))})
        return jwks

    def _get_signing_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")

        if alg not in self.algorithms:
                    logger.info("auth.token.invalid_algorithm", extra={"alg": alg, "allowed": list(self.algorithms)})
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token algorithm")
        
        jwks = self._fetch_jwks()
        
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                return PyJWK.from_dict(key).key

        self._jwks = None
        logger.info("auth.jwks.kid_miss.refresh", extra={"kid": kid})
        jwks = self._fetch_jwks()
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                return PyJWK.from_dict(key).key

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown token key id")

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            signing_key = self._get_signing_key(token)
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.clock_skew_seconds,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            logger.exception("auth.jwks.fetch.error")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="unable to fetch jwks",
            ) from exc
        except InvalidTokenError as exc:
            logger.info("auth.token.invalid", extra={"error": exc.__class__.__name__})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
            ) from exc

        subject = claims.get("sub")
        try:
            user_id = UUID(str(subject))
        except (TypeError, ValueError) as exc:
            logger.info("auth.token.invalid_subject")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token subject"
            ) from exc

        logger.debug("auth.token.verified", extra={"user_id": str(user_id), "issuer": self.issuer})
        return AuthenticatedUser(user_id=user_id, claims=claims)


def build_verifier() -> SupabaseJWTVerifier:
    issuer = settings.auth_issuer
    jwks_url = settings.auth_jwks_url

    if not issuer and settings.supabase_url:
        issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    if not jwks_url and issuer:
        jwks_url = f"{issuer.rstrip('/')}/.well-known/jwks.json"

    if not issuer or not jwks_url:
        raise RuntimeError("AUTH_ISSUER/AUTH_JWKS_URL or SUPABASE_URL must be configured")

    logger.info(
        "auth.verifier.configured",
        extra={
            "issuer": issuer,
            "audience": settings.auth_audience,
            "jwks_url": jwks_url,
            "algorithms": settings.auth_jwt_algorithms,
            "jwks_cache_ttl_seconds": settings.auth_jwks_cache_ttl_seconds,
            "clock_skew_seconds": settings.auth_clock_skew_seconds,
        },
    )

    return SupabaseJWTVerifier(
        issuer=issuer,
        audience=settings.auth_audience,
        jwks_url=jwks_url,
        algorithms=tuple(settings.auth_jwt_algorithms),
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
        clock_skew_seconds=settings.auth_clock_skew_seconds,
    )
