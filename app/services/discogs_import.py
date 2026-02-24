from __future__ import annotations

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import redact_sensitive_data
from app.core.token_crypto import TokenCrypto
from app.db import models
from app.services.notifications import enqueue_from_event
from app.services.watch_rules import ensure_user_exists

BASE_URL = "https://api.discogs.com"
AUTHORIZE_URL = "https://www.discogs.com/oauth/authorize"
TOKEN_URL = "https://api.discogs.com/oauth/access_token"
REVOKE_URL = "https://api.discogs.com/oauth/revoke"


class DiscogsImportService:
    def __init__(self) -> None:
        self._base_headers = {"User-Agent": settings.discogs_user_agent}
        self._token_crypto = TokenCrypto.from_settings(settings)

    def connect_account(
        self,
        db: Session,
        *,
        user_id: UUID,
        external_user_id: str,
        access_token: str | None,
        token_metadata: dict[str, Any] | None,
    ) -> models.ExternalAccountLink:
        ensure_user_exists(db, user_id)
        now = datetime.now(timezone.utc)

        link = (
            db.query(models.ExternalAccountLink)
            .filter(models.ExternalAccountLink.user_id == user_id)
            .filter(models.ExternalAccountLink.provider == models.Provider.discogs)
            .first()
        )
        if not link:
            link = models.ExternalAccountLink(
                user_id=user_id,
                provider=models.Provider.discogs,
                external_user_id=external_user_id,
                access_token=self._encrypt_access_token(access_token),
                token_metadata=token_metadata,
                connected_at=now,
                created_at=now,
                updated_at=now,
            )
        else:
            link.external_user_id = external_user_id
            link.access_token = self._encrypt_access_token(access_token)
            link.token_metadata = token_metadata
            link.connected_at = now
            link.updated_at = now

        db.add(link)
        db.flush()
        db.refresh(link)
        return link

    def start_oauth(
        self,
        db: Session,
        *,
        user_id: UUID,
        scopes: list[str] | None,
    ) -> dict[str, Any]:
        ensure_user_exists(db, user_id)
        now = datetime.now(timezone.utc)
        requested_scopes = scopes or [s for s in settings.discogs_oauth_scopes.split(" ") if s]
        state = token_urlsafe(24)
        expires_at = now + timedelta(seconds=settings.discogs_oauth_state_ttl_seconds)

        metadata = {
            "oauth_state": state,
            "oauth_state_expires_at": expires_at.isoformat(),
            "oauth_scopes": requested_scopes,
            "oauth_connected": False,
        }
        link = self.connect_account(
            db,
            user_id=user_id,
            external_user_id="pending",
            access_token=None,
            token_metadata=metadata,
        )
        link.connected_at = now
        link.updated_at = now
        db.add(link)
        db.flush()

        params = {
            "client_id": settings.discogs_oauth_client_id,
            "response_type": "code",
            "redirect_uri": settings.discogs_oauth_redirect_uri,
            "scope": " ".join(requested_scopes),
            "state": state,
        }
        query = urlencode({k: v for k, v in params.items() if v})
        return {
            "provider": models.Provider.discogs.value,
            "authorize_url": f"{AUTHORIZE_URL}?{query}",
            "state": state,
            "scopes": requested_scopes,
            "expires_at": expires_at,
        }

    def complete_oauth(
        self,
        db: Session,
        *,
        user_id: UUID,
        state: str,
        code: str,
    ) -> models.ExternalAccountLink:
        link = self.get_status(db, user_id=user_id)
        if not link:
            raise HTTPException(status_code=400, detail="OAuth session not started")

        metadata = link.token_metadata or {}
        expected_state = metadata.get("oauth_state")
        expires_raw = metadata.get("oauth_state_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if not expected_state or expected_state != state:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")
        if expires_at and datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=400, detail="OAuth state expired")

        token_resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discogs_oauth_redirect_uri,
                "client_id": settings.discogs_oauth_client_id,
                "client_secret": settings.discogs_oauth_client_secret,
            },
            timeout=settings.discogs_timeout_seconds,
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Discogs token exchange failed")
        token_payload = token_resp.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise HTTPException(status_code=502, detail="Discogs token exchange missing access_token")

        identity_resp = httpx.get(
            f"{BASE_URL}/oauth/identity",
            headers={**self._base_headers, "Authorization": f"Discogs token={access_token}"},
            timeout=settings.discogs_timeout_seconds,
        )
        if identity_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Discogs identity lookup failed")

        identity = identity_resp.json()
        username = str(identity.get("username") or "").strip()
        if not username:
            raise HTTPException(status_code=502, detail="Discogs identity missing username")

        completed_metadata = {
            **metadata,
            "oauth_state": None,
            "oauth_state_expires_at": None,
            "oauth_connected": True,
            "oauth_scopes": metadata.get("oauth_scopes") or token_payload.get("scope", "").split(" "),
            "token_type": token_payload.get("token_type"),
        }
        return self.connect_account(
            db,
            user_id=user_id,
            external_user_id=username,
            access_token=access_token,
            token_metadata=completed_metadata,
        )

    def disconnect_account(self, db: Session, *, user_id: UUID, revoke: bool) -> bool:
        link = self.get_status(db, user_id=user_id)
        if not link:
            return False

        decrypted_token = self._get_decrypted_access_token(db, link=link)
        if revoke and decrypted_token:
            try:
                httpx.post(
                    REVOKE_URL,
                    data={"token": decrypted_token, "client_id": settings.discogs_oauth_client_id},
                    timeout=settings.discogs_timeout_seconds,
                )
            except Exception:
                pass

        db.delete(link)
        db.flush()
        return True

    def get_status(self, db: Session, *, user_id: UUID) -> models.ExternalAccountLink | None:
        link = (
            db.query(models.ExternalAccountLink)
            .filter(models.ExternalAccountLink.user_id == user_id)
            .filter(models.ExternalAccountLink.provider == models.Provider.discogs)
            .first()
        )
        if not link:
            return None

        self._ensure_token_encrypted(db, link=link)
        return link

    def run_import(
        self,
        db: Session,
        *,
        user_id: UUID,
        source: str,
    ) -> models.ImportJob:
        link = self.get_status(db, user_id=user_id)
        if not link:
            raise HTTPException(status_code=400, detail="Discogs is not connected")
        access_token = self._get_decrypted_access_token(db, link=link)
        if not access_token:
            raise HTTPException(status_code=400, detail="Discogs OAuth callback not completed")

        now = datetime.now(timezone.utc)
        job = models.ImportJob(
            user_id=user_id,
            external_account_link_id=link.id,
            provider=models.Provider.discogs,
            import_scope=source,
            status="running",
            page=1,
            cursor=None,
            processed_count=0,
            imported_count=0,
            created_count=0,
            updated_count=0,
            error_count=0,
            errors=[],
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()

        self._emit_import_event(
            db,
            user_id=user_id,
            event_type=models.EventType.IMPORT_STARTED,
            payload={"job_id": str(job.id), "source": source},
        )

        try:
            import_sources = ["wantlist", "collection"] if source == "both" else [source]
            for selected_source in import_sources:
                self._import_source(db, link=link, job=job, source=selected_source, access_token=access_token)

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            self._emit_import_event(
                db,
                user_id=user_id,
                event_type=models.EventType.IMPORT_COMPLETED,
                payload={
                    "job_id": str(job.id),
                    "source": source,
                    "processed_count": job.processed_count,
                    "imported_count": job.imported_count,
                },
            )
        except Exception as exc:
            job.status = "failed"
            job.error_count += 1
            safe_error = str(redact_sensitive_data(str(exc)))
            job.errors = [*(job.errors or []), {"error": safe_error}]
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            self._emit_import_event(
                db,
                user_id=user_id,
                event_type=models.EventType.IMPORT_FAILED,
                payload={"job_id": str(job.id), "source": source, "error": safe_error},
            )

        db.add(job)
        db.flush()
        db.refresh(job)
        return job

    def get_job(self, db: Session, *, user_id: UUID, job_id: UUID) -> models.ImportJob:
        job = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.id == job_id)
            .filter(models.ImportJob.user_id == user_id)
            .first()
        )
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")
        return job

    def _import_source(
        self,
        db: Session,
        *,
        link: models.ExternalAccountLink,
        job: models.ImportJob,
        source: str,
        access_token: str,
    ) -> None:
        endpoint = self._endpoint_for(source=source, username=link.external_user_id)
        page = 1
        pages = 1

        while page <= pages:
            data = self._fetch_page(endpoint=endpoint, token=access_token, page=page)
            pages = int((data.get("pagination") or {}).get("pages") or 1)
            releases = data.get("releases") or data.get("wants") or []

            for raw_release in releases:
                normalized = self._normalize_release(raw_release)
                if not normalized:
                    continue

                created = self._upsert_watch_release(db, user_id=job.user_id, normalized=normalized)
                job.processed_count += 1
                job.imported_count += 1
                if created:
                    job.created_count += 1
                else:
                    job.updated_count += 1

            job.page = page
            job.cursor = f"{source}:{page}/{pages}"
            job.updated_at = datetime.now(timezone.utc)
            db.add(job)
            db.flush()
            page += 1

    def _endpoint_for(self, *, source: str, username: str) -> str:
        if source == "wantlist":
            return f"/users/{username}/wants"
        if source == "collection":
            return f"/users/{username}/collection/folders/0/releases"
        raise HTTPException(status_code=400, detail="Unsupported Discogs import source")

    def _fetch_page(self, *, endpoint: str, token: str | None, page: int) -> dict[str, Any]:
        headers = dict(self._base_headers)
        auth_token = token or settings.discogs_token
        if auth_token:
            headers["Authorization"] = f"Discogs token={auth_token}"

        response = httpx.get(
            f"{BASE_URL}{endpoint}",
            headers=headers,
            params={"page": page, "per_page": 100},
            timeout=settings.discogs_timeout_seconds,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Discogs import failed with {response.status_code}")
        return response.json()

    def _normalize_release(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        basic = raw.get("basic_information") or raw
        release_id = basic.get("id") or raw.get("id")
        if not release_id:
            return None

        artists = basic.get("artists") or []
        artist = None
        if artists:
            artist = str((artists[0] or {}).get("name") or "").strip() or None

        title = str(basic.get("title") or raw.get("title") or "").strip()
        if not title:
            return None

        year = basic.get("year") or raw.get("year")
        try:
            normalized_year = int(year) if year else None
        except (TypeError, ValueError):
            normalized_year = None

        return {
            "discogs_release_id": int(release_id),
            "title": title,
            "artist": artist,
            "year": normalized_year,
        }

    def _upsert_watch_release(self, db: Session, *, user_id: UUID, normalized: dict[str, Any]) -> bool:
        existing = (
            db.query(models.WatchRelease)
            .filter(models.WatchRelease.user_id == user_id)
            .filter(models.WatchRelease.discogs_release_id == normalized["discogs_release_id"])
            .first()
        )
        now = datetime.now(timezone.utc)

        if existing:
            existing.title = normalized["title"]
            existing.artist = normalized.get("artist")
            existing.year = normalized.get("year")
            existing.is_active = True
            existing.updated_at = now
            db.add(existing)
            return False

        watch = models.WatchRelease(
            user_id=user_id,
            discogs_release_id=normalized["discogs_release_id"],
            title=normalized["title"],
            artist=normalized.get("artist"),
            year=normalized.get("year"),
            currency="USD",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(watch)
        return True

    def _encrypt_access_token(self, access_token: str | None) -> str | None:
        return self._token_crypto.encrypt(access_token)

    def _ensure_token_encrypted(self, db: Session, *, link: models.ExternalAccountLink) -> None:
        if not link.access_token or self._token_crypto.is_encrypted(link.access_token):
            return

        link.access_token = self._encrypt_access_token(link.access_token)
        link.updated_at = datetime.now(timezone.utc)
        db.add(link)
        db.flush()

    def _get_decrypted_access_token(self, db: Session, *, link: models.ExternalAccountLink) -> str | None:
        if not link.access_token:
            return None

        result = self._token_crypto.decrypt(link.access_token)
        if result.requires_migration:
            link.access_token = self._encrypt_access_token(result.plaintext)
            link.updated_at = datetime.now(timezone.utc)
            db.add(link)
            db.flush()
        return result.plaintext

    def _emit_import_event(
        self,
        db: Session,
        *,
        user_id: UUID,
        event_type: models.EventType,
        payload: dict[str, Any],
    ) -> None:
        event = models.Event(
            user_id=user_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.flush()
        enqueue_from_event(db, event=event)


discogs_import_service = DiscogsImportService()
