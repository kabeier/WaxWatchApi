from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm

from app.core.config import settings


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

        response = httpx.get(self.jwks_url, timeout=5.0)
        response.raise_for_status()
        jwks = response.json()
        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="invalid jwks response"
            )

        self._jwks = jwks
        self._jwks_loaded_at = now
        return jwks

    def _get_signing_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")

        if alg not in self.algorithms:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token algorithm")

        jwks = self._fetch_jwks()
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                return RSAAlgorithm.from_jwk(json.dumps(key))

        self._jwks = None
        jwks = self._fetch_jwks()
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                return RSAAlgorithm.from_jwk(json.dumps(key))

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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="unable to fetch jwks",
            ) from exc
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
            ) from exc

        subject = claims.get("sub")
        try:
            user_id = UUID(str(subject))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token subject"
            ) from exc

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

    return SupabaseJWTVerifier(
        issuer=issuer,
        audience=settings.auth_audience,
        jwks_url=jwks_url,
        algorithms=tuple(settings.auth_jwt_algorithms),
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
        clock_skew_seconds=settings.auth_clock_skew_seconds,
    )
