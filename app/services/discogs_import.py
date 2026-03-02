from __future__ import annotations

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import redact_sensitive_data
from app.core.token_crypto import TokenCrypto
from app.db import models
from app.services.notifications import enqueue_from_event
from app.services.token_lifecycle import is_token_expired
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
        refresh_token: str | None = None,
        access_token_expires_at: datetime | None = None,
        token_type: str | None = None,
        scopes: list[str] | None = None,
    ) -> models.ExternalAccountLink:
        ensure_user_exists(db, user_id)
        now = datetime.now(timezone.utc)
        normalized_refresh_token = refresh_token or self._metadata_string(token_metadata, "refresh_token")
        normalized_token_type = token_type or self._metadata_string(token_metadata, "token_type")
        normalized_scopes = scopes or self._metadata_scopes(token_metadata)
        normalized_expiry = access_token_expires_at or self._metadata_datetime(
            token_metadata, "access_token_expires_at", "expires_at"
        )

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
                refresh_token=normalized_refresh_token,
                access_token_expires_at=normalized_expiry,
                token_type=normalized_token_type,
                scopes=normalized_scopes,
                connected_at=now,
                created_at=now,
                updated_at=now,
            )
        else:
            link.external_user_id = external_user_id
            link.access_token = self._encrypt_access_token(access_token)
            link.token_metadata = token_metadata
            link.refresh_token = normalized_refresh_token or link.refresh_token
            link.access_token_expires_at = normalized_expiry or link.access_token_expires_at
            link.token_type = normalized_token_type or link.token_type
            link.scopes = normalized_scopes or link.scopes
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
        expires_at = self._metadata_datetime(metadata, "oauth_state_expires_at")
        if not expected_state or expected_state != state:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")
        if is_token_expired(expires_at):
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

        normalized_scopes = metadata.get("oauth_scopes") or self._split_scope_string(
            token_payload.get("scope")
        )
        completed_metadata = {
            **metadata,
            "oauth_state": None,
            "oauth_state_expires_at": None,
            "oauth_connected": True,
            "oauth_scopes": normalized_scopes,
            "token_type": token_payload.get("token_type"),
            "refresh_token": token_payload.get("refresh_token"),
            "access_token_expires_at": token_payload.get("expires_at"),
        }
        return self.connect_account(
            db,
            user_id=user_id,
            external_user_id=username,
            access_token=access_token,
            token_metadata=completed_metadata,
            refresh_token=token_payload.get("refresh_token"),
            token_type=token_payload.get("token_type"),
            scopes=normalized_scopes,
            access_token_expires_at=self._expires_at_from_token_payload(token_payload),
        )

    @staticmethod
    def _split_scope_string(scope: str | None) -> list[str]:
        if not scope:
            return []
        return [value for value in scope.split(" ") if value]

    @classmethod
    def _metadata_scopes(cls, token_metadata: dict[str, Any] | None) -> list[str] | None:
        if not token_metadata:
            return None
        scopes = token_metadata.get("oauth_scopes") or token_metadata.get("scopes")
        if isinstance(scopes, list):
            return [str(value) for value in scopes if str(value).strip()]
        if isinstance(scopes, str):
            return cls._split_scope_string(scopes)
        scope = token_metadata.get("scope")
        if isinstance(scope, str):
            return cls._split_scope_string(scope)
        return None

    @staticmethod
    def _metadata_string(token_metadata: dict[str, Any] | None, key: str) -> str | None:
        if not token_metadata:
            return None
        value = token_metadata.get(key)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _metadata_datetime(token_metadata: dict[str, Any] | None, *keys: str) -> datetime | None:
        if not token_metadata:
            return None
        for key in keys:
            raw_value = token_metadata.get(key)
            if not raw_value:
                continue
            if isinstance(raw_value, datetime):
                return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
            if isinstance(raw_value, (int, float)):
                return datetime.fromtimestamp(raw_value, tz=timezone.utc)
            if isinstance(raw_value, str):
                candidate = raw_value.strip()
                if not candidate:
                    continue
                try:
                    parsed = datetime.fromisoformat(candidate)
                except ValueError:
                    continue
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None

    @classmethod
    def _expires_at_from_token_payload(cls, token_payload: dict[str, Any]) -> datetime | None:
        expires_in = token_payload.get("expires_in")
        if isinstance(expires_in, (int, float)):
            return datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))
        return cls._metadata_datetime(token_payload, "access_token_expires_at", "expires_at")

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

        self._ensure_normalized_lifecycle_fields(db, link=link)
        self._ensure_token_encrypted(db, link=link)
        return link

    def _ensure_normalized_lifecycle_fields(self, db: Session, *, link: models.ExternalAccountLink) -> None:
        metadata = link.token_metadata if isinstance(link.token_metadata, dict) else None
        if not metadata:
            return

        normalized_refresh_token = self._metadata_string(metadata, "refresh_token")
        normalized_token_type = self._metadata_string(metadata, "token_type")
        normalized_scopes = self._metadata_scopes(metadata)
        normalized_expiry = self._metadata_datetime(metadata, "access_token_expires_at", "expires_at")

        changed = False
        if link.refresh_token is None and normalized_refresh_token is not None:
            link.refresh_token = normalized_refresh_token
            changed = True
        if link.token_type is None and normalized_token_type is not None:
            link.token_type = normalized_token_type
            changed = True
        if link.scopes is None and normalized_scopes is not None:
            link.scopes = normalized_scopes
            changed = True
        if link.access_token_expires_at is None and normalized_expiry is not None:
            link.access_token_expires_at = normalized_expiry
            changed = True

        if changed:
            link.updated_at = datetime.now(timezone.utc)
            db.add(link)
            db.flush()

    def list_sync_candidates(self, db: Session, *, limit: int) -> list[models.ExternalAccountLink]:
        normalized_limit = max(limit, 0)
        if normalized_limit == 0:
            return []

        return (
            db.query(models.ExternalAccountLink)
            .join(models.User, models.User.id == models.ExternalAccountLink.user_id)
            .filter(models.ExternalAccountLink.provider == models.Provider.discogs)
            .filter(models.ExternalAccountLink.external_user_id != "pending")
            .filter(models.ExternalAccountLink.access_token.isnot(None))
            .filter(models.User.is_active.is_(True))
            .order_by(models.ExternalAccountLink.updated_at.asc(), models.ExternalAccountLink.id.asc())
            .limit(normalized_limit)
            .all()
        )

    def run_import(
        self,
        db: Session,
        *,
        user_id: UUID,
        source: str,
    ) -> models.ImportJob:
        job, _created = self.ensure_import_job(db, user_id=user_id, source=source)
        return job

    def create_import_job(
        self,
        db: Session,
        *,
        user_id: UUID,
        source: str,
    ) -> models.ImportJob:
        job, _created = self.ensure_import_job(db, user_id=user_id, source=source)
        return job

    def ensure_import_job(
        self,
        db: Session,
        *,
        user_id: UUID,
        source: str,
        cooldown_seconds: int | None = None,
    ) -> tuple[models.ImportJob, bool]:
        link = self.get_status(db, user_id=user_id)
        if not link:
            raise HTTPException(status_code=400, detail="Discogs is not connected")
        access_token = self._get_decrypted_access_token(db, link=link)
        if not access_token:
            raise HTTPException(status_code=400, detail="Discogs OAuth callback not completed")

        now = datetime.now(timezone.utc)
        job_id = uuid4()
        insert_stmt = (
            postgresql_insert(models.ImportJob.__table__)
            .values(
                id=job_id,
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
            .on_conflict_do_nothing(
                index_elements=["user_id", "provider", "import_scope"],
                index_where=models.ImportJob.status.in_(["pending", "running"]),
            )
        )
        inserted_job_id = db.execute(insert_stmt.returning(models.ImportJob.id)).scalar_one_or_none()

        if inserted_job_id is None:
            in_flight_job = (
                db.query(models.ImportJob)
                .filter(models.ImportJob.user_id == user_id)
                .filter(models.ImportJob.provider == models.Provider.discogs)
                .filter(models.ImportJob.import_scope == source)
                .filter(models.ImportJob.status.in_(["pending", "running"]))
                .order_by(models.ImportJob.created_at.desc())
                .first()
            )
            if in_flight_job:
                return in_flight_job, False
            raise HTTPException(status_code=409, detail="Concurrent import job creation conflict")

        job = db.query(models.ImportJob).filter(models.ImportJob.id == inserted_job_id).one()

        if cooldown_seconds and cooldown_seconds > 0:
            cooldown_cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
            recent_job = (
                db.query(models.ImportJob)
                .filter(models.ImportJob.user_id == user_id)
                .filter(models.ImportJob.provider == models.Provider.discogs)
                .filter(models.ImportJob.import_scope == source)
                .filter(models.ImportJob.id != inserted_job_id)
                .filter(models.ImportJob.created_at >= cooldown_cutoff)
                .order_by(models.ImportJob.created_at.desc())
                .first()
            )
            if recent_job:
                db.delete(job)
                db.flush()
                return recent_job, False

        self._emit_import_event(
            db,
            user_id=user_id,
            event_type=models.EventType.IMPORT_STARTED,
            payload={"job_id": str(job.id), "source": source},
        )
        return job, True

    def execute_import_job(self, db: Session, *, job_id: UUID) -> models.ImportJob:
        job = db.query(models.ImportJob).filter(models.ImportJob.id == job_id).one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")
        if job.status != "running":
            return job

        link = (
            db.query(models.ExternalAccountLink)
            .filter(models.ExternalAccountLink.id == job.external_account_link_id)
            .one()
        )
        access_token = self._get_decrypted_access_token(db, link=link)
        if not access_token:
            raise HTTPException(status_code=400, detail="Discogs OAuth callback not completed")

        source = job.import_scope
        try:
            import_sources = ["wantlist", "collection"] if source == "both" else [source]
            for selected_source in import_sources:
                self._import_source(db, link=link, job=job, source=selected_source, access_token=access_token)

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            self._emit_import_event(
                db,
                user_id=job.user_id,
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
                user_id=job.user_id,
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

                created = self._upsert_watch_release(
                    db,
                    user_id=job.user_id,
                    normalized=normalized,
                    source=source,
                )
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

        master_id = basic.get("master_id") or raw.get("master_id")

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

        normalized_master_id = None
        try:
            normalized_master_id = int(master_id) if master_id else None
        except (TypeError, ValueError):
            normalized_master_id = None

        return {
            "discogs_release_id": int(release_id),
            "discogs_master_id": normalized_master_id,
            "match_mode": "exact_release",
            "title": title,
            "artist": artist,
            "year": normalized_year,
        }

    def _upsert_watch_release(
        self,
        db: Session,
        *,
        user_id: UUID,
        normalized: dict[str, Any],
        source: Literal["wantlist", "collection"],
    ) -> bool:
        existing = (
            db.query(models.WatchRelease)
            .filter(models.WatchRelease.user_id == user_id)
            .filter(models.WatchRelease.discogs_release_id == normalized["discogs_release_id"])
            .first()
        )
        now = datetime.now(timezone.utc)

        if existing:
            existing.discogs_master_id = normalized.get("discogs_master_id")
            existing.match_mode = normalized.get("match_mode") or existing.match_mode
            existing.title = normalized["title"]
            existing.artist = normalized.get("artist")
            existing.year = normalized.get("year")
            existing.is_active = True
            existing.imported_from_wantlist = existing.imported_from_wantlist or source == "wantlist"
            existing.imported_from_collection = existing.imported_from_collection or source == "collection"
            existing.updated_at = now
            db.add(existing)
            return False

        watch = models.WatchRelease(
            user_id=user_id,
            discogs_release_id=normalized["discogs_release_id"],
            discogs_master_id=normalized.get("discogs_master_id"),
            match_mode=normalized.get("match_mode") or "exact_release",
            title=normalized["title"],
            artist=normalized.get("artist"),
            year=normalized.get("year"),
            currency="USD",
            is_active=True,
            imported_from_wantlist=source == "wantlist",
            imported_from_collection=source == "collection",
            created_at=now,
            updated_at=now,
        )
        db.add(watch)
        return True

    def list_imported_items(
        self,
        db: Session,
        *,
        user_id: UUID,
        source: Literal["wantlist", "collection"],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        ensure_user_exists(db, user_id)

        source_filter = (
            models.WatchRelease.imported_from_wantlist.is_(True)
            if source == "wantlist"
            else models.WatchRelease.imported_from_collection.is_(True)
        )

        query = (
            db.query(models.WatchRelease)
            .filter(models.WatchRelease.user_id == user_id)
            .filter(models.WatchRelease.is_active.is_(True))
            .filter(source_filter)
        )

        items = (
            query.order_by(models.WatchRelease.updated_at.desc(), models.WatchRelease.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return {
            "source": source,
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "items": [
                {
                    "watch_release_id": item.id,
                    "discogs_release_id": item.discogs_release_id,
                    "discogs_master_id": item.discogs_master_id,
                    "title": item.title,
                    "artist": item.artist,
                    "year": item.year,
                    "source": source,
                    "open_in_discogs_url": self._discogs_release_url(item.discogs_release_id),
                }
                for item in items
            ],
        }

    def get_open_in_discogs_link(
        self,
        db: Session,
        *,
        user_id: UUID,
        watch_release_id: UUID,
        source: Literal["wantlist", "collection"],
    ) -> dict[str, Any]:
        source_filter = (
            models.WatchRelease.imported_from_wantlist.is_(True)
            if source == "wantlist"
            else models.WatchRelease.imported_from_collection.is_(True)
        )
        watch = (
            db.query(models.WatchRelease)
            .filter(models.WatchRelease.user_id == user_id)
            .filter(models.WatchRelease.id == watch_release_id)
            .filter(models.WatchRelease.is_active.is_(True))
            .filter(source_filter)
            .first()
        )
        if not watch:
            raise HTTPException(status_code=404, detail="Imported Discogs item not found for source")

        return {
            "watch_release_id": watch.id,
            "source": source,
            "open_in_discogs_url": self._discogs_release_url(watch.discogs_release_id),
        }

    def _discogs_release_url(self, discogs_release_id: int) -> str:
        return f"https://www.discogs.com/release/{discogs_release_id}"

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
