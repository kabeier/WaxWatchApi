from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.token_lifecycle import is_token_expired, should_refresh_access_token


def test_token_expiry_and_refresh_eligibility() -> None:
    now = datetime.now(timezone.utc)
    assert is_token_expired(now - timedelta(seconds=1), now=now) is True
    assert is_token_expired(now + timedelta(seconds=1), now=now) is False

    assert (
        should_refresh_access_token(
            refresh_token="refresh",
            access_token_expires_at=now + timedelta(seconds=20),
            now=now,
        )
        is True
    )
    assert (
        should_refresh_access_token(
            refresh_token="refresh",
            access_token_expires_at=now + timedelta(minutes=10),
            now=now,
        )
        is False
    )
    assert (
        should_refresh_access_token(
            refresh_token=None,
            access_token_expires_at=now - timedelta(seconds=1),
            now=now,
        )
        is False
    )


def test_migration_backfill_extractor_normalizes_metadata() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "ab12cd34ef56_normalize_external_account_token_fields.py"
    )
    spec = importlib.util.spec_from_file_location("token_fields_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    values = module.extract_normalized_token_fields(
        {
            "refresh_token": "refresh-me",
            "token_type": "Bearer",
            "scope": "identity wantlist",
            "expires_at": "2030-01-01T00:00:00+00:00",
        }
    )
    assert values["refresh_token"] == "refresh-me"
    assert values["token_type"] == "Bearer"
    assert values["access_token_expires_at"] == "2030-01-01T00:00:00+00:00"
    assert values["scopes"] == ["identity", "wantlist"]
