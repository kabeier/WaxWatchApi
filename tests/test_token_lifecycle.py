from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.discogs_import import DiscogsImportService
from app.services.token_lifecycle import is_token_expired, should_refresh_access_token


def _load_migration_module():
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
    return module


def test_token_expiry_and_refresh_eligibility() -> None:
    now = datetime.now(timezone.utc)
    assert is_token_expired(None, now=now) is False
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
            refresh_token="refresh",
            access_token_expires_at=None,
            now=now,
        )
        is True
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
    module = _load_migration_module()

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


def test_migration_backfill_extractor_handles_array_and_empty_inputs() -> None:
    module = _load_migration_module()

    assert module.extract_normalized_token_fields(None) == {
        "refresh_token": None,
        "token_type": None,
        "access_token_expires_at": None,
        "scopes": None,
    }

    values = module.extract_normalized_token_fields(
        {
            "refresh_token": "refresh-array",
            "token_type": "bearer",
            "access_token_expires_at": "2031-01-01T00:00:00+00:00",
            "oauth_scopes": ["identity", "", "wantlist"],
        }
    )
    assert values["refresh_token"] == "refresh-array"
    assert values["token_type"] == "bearer"
    assert values["access_token_expires_at"] == "2031-01-01T00:00:00+00:00"
    assert values["scopes"] == ["identity", "wantlist"]


def test_discogs_token_metadata_normalizers_cover_datetime_and_scope_variants() -> None:
    now = datetime.now(timezone.utc)
    service = DiscogsImportService()

    assert service._split_scope_string(None) == []
    assert service._split_scope_string("identity wantlist") == ["identity", "wantlist"]

    assert service._metadata_scopes({"oauth_scopes": ["identity", "", "wantlist"]}) == [
        "identity",
        "wantlist",
    ]
    assert service._metadata_scopes({"scopes": "identity collection"}) == ["identity", "collection"]
    assert service._metadata_scopes({"scope": "identity inventory"}) == ["identity", "inventory"]
    assert service._metadata_scopes({"scope": 1}) is None

    assert service._metadata_string({"token_type": " Bearer "}, "token_type") == "Bearer"
    assert service._metadata_string({"token_type": "   "}, "token_type") is None
    assert service._metadata_string(None, "token_type") is None

    assert service._metadata_datetime({"expires": now}, "expires") == now
    naive_now = datetime.now()
    parsed_naive = service._metadata_datetime({"expires": naive_now}, "expires")
    assert parsed_naive is not None and parsed_naive.tzinfo == timezone.utc

    parsed_epoch = service._metadata_datetime({"expires": 1735689600}, "expires")
    assert parsed_epoch == datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)

    parsed_iso = service._metadata_datetime(
        {"expires": "2030-01-01T00:00:00+00:00", "fallback": "not-used"},
        "expires",
        "fallback",
    )
    assert parsed_iso == datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert service._metadata_datetime({"expires": "bad-date"}, "expires") is None


def test_discogs_expires_at_from_token_payload_prefers_expires_in() -> None:
    service = DiscogsImportService()
    with_expires_in = service._expires_at_from_token_payload({"expires_in": 60})
    assert with_expires_in is not None

    with_iso = service._expires_at_from_token_payload(
        {"access_token_expires_at": "2030-01-01T00:00:00+00:00"}
    )
    assert with_iso == datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)

    with_none = service._expires_at_from_token_payload({})
    assert with_none is None
