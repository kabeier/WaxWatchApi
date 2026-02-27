from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

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


def _load_backfill_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "7c9e1f2a4b6d_backfill_external_account_lifecycle_fields.py"
    )
    spec = importlib.util.spec_from_file_location("token_fields_backfill_migration", migration_path)
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


def _select_scope_debug_row(db_session: sa.orm.Session, *, link_id) -> dict[str, object | None]:
    return (
        db_session.execute(
            sa.text(
                """
                WITH scope_sources AS (
                    SELECT
                        eal.id,
                        CASE
                            WHEN jsonb_typeof(eal.token_metadata -> 'oauth_scopes') = 'array' THEN (
                                SELECT to_jsonb(ARRAY_AGG(token))
                                FROM (
                                    SELECT BTRIM(value) AS token
                                    FROM jsonb_array_elements_text(eal.token_metadata -> 'oauth_scopes')
                                ) normalized
                                WHERE token <> ''
                            )
                            ELSE NULL
                        END AS oauth_scopes_jsonb,
                        CASE
                            WHEN jsonb_typeof(eal.token_metadata -> 'scopes') = 'array' THEN (
                                SELECT to_jsonb(ARRAY_AGG(token))
                                FROM (
                                    SELECT BTRIM(value) AS token
                                    FROM jsonb_array_elements_text(eal.token_metadata -> 'scopes')
                                ) normalized
                                WHERE token <> ''
                            )
                            ELSE NULL
                        END AS scopes_array_jsonb,
                        (
                            SELECT
                                CASE
                                    WHEN NULLIF(normalized_scope_text, '') IS NULL THEN NULL
                                    ELSE to_jsonb(array_remove(string_to_array(normalized_scope_text, ' '), ''))
                                END
                            FROM (
                                SELECT BTRIM(
                                    regexp_replace(
                                        COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope'),
                                        E'[[:space:]]+',
                                        ' ',
                                        'g'
                                    )
                                ) AS normalized_scope_text
                            ) text_scope
                        ) AS scopes_text_jsonb,
                        COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope') AS raw_scope_text,
                        BTRIM(
                            regexp_replace(
                                COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope'),
                                E'[[:space:]]+',
                                ' ',
                                'g'
                            )
                        ) AS normalized_scope_text,
                        eal.scopes AS persisted_scopes
                    FROM external_account_links AS eal
                    WHERE eal.id = :id
                )
                SELECT
                    raw_scope_text,
                    normalized_scope_text,
                    oauth_scopes_jsonb,
                    scopes_array_jsonb,
                    scopes_text_jsonb,
                    COALESCE(
                        CASE
                            WHEN oauth_scopes_jsonb IS NOT NULL
                                AND jsonb_array_length(oauth_scopes_jsonb) > 0 THEN oauth_scopes_jsonb
                            ELSE NULL
                        END,
                        CASE
                            WHEN scopes_array_jsonb IS NOT NULL
                                AND jsonb_array_length(scopes_array_jsonb) > 0 THEN scopes_array_jsonb
                            ELSE NULL
                        END,
                        CASE
                            WHEN scopes_text_jsonb IS NOT NULL
                                AND jsonb_array_length(scopes_text_jsonb) > 0 THEN scopes_text_jsonb
                            ELSE NULL
                        END
                    ) AS normalized_scope_jsonb,
                    persisted_scopes
                FROM scope_sources
                """
            ),
            {"id": link_id},
        )
        .mappings()
        .one()
    )


def _select_scope_update_predicate_state(db_session: sa.orm.Session, *, link_id) -> dict[str, object | None]:
    return (
        db_session.execute(
            sa.text(
                """
                WITH scope_sources AS (
                    SELECT
                        eal.id,
                        CASE
                            WHEN jsonb_typeof(eal.token_metadata -> 'oauth_scopes') = 'array' THEN (
                                SELECT to_jsonb(ARRAY_AGG(token))
                                FROM (
                                    SELECT BTRIM(value) AS token
                                    FROM jsonb_array_elements_text(eal.token_metadata -> 'oauth_scopes')
                                ) normalized
                                WHERE token <> ''
                            )
                            ELSE NULL
                        END AS oauth_scopes_jsonb,
                        CASE
                            WHEN jsonb_typeof(eal.token_metadata -> 'scopes') = 'array' THEN (
                                SELECT to_jsonb(ARRAY_AGG(token))
                                FROM (
                                    SELECT BTRIM(value) AS token
                                    FROM jsonb_array_elements_text(eal.token_metadata -> 'scopes')
                                ) normalized
                                WHERE token <> ''
                            )
                            ELSE NULL
                        END AS scopes_array_jsonb,
                        (
                            SELECT
                                CASE
                                    WHEN NULLIF(normalized_scope_text, '') IS NULL THEN NULL
                                    ELSE to_jsonb(array_remove(string_to_array(normalized_scope_text, ' '), ''))
                                END
                            FROM (
                                SELECT BTRIM(
                                    regexp_replace(
                                        COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope'),
                                        E'[[:space:]]+',
                                        ' ',
                                        'g'
                                    )
                                ) AS normalized_scope_text
                            ) text_scope
                        ) AS scopes_text_jsonb,
                        eal.scopes AS persisted_scopes
                    FROM external_account_links AS eal
                    WHERE eal.id = :id
                ),
                scope_normalized AS (
                    SELECT
                        ss.id,
                        COALESCE(
                            CASE
                                WHEN ss.oauth_scopes_jsonb IS NOT NULL
                                    AND jsonb_array_length(ss.oauth_scopes_jsonb) > 0 THEN ss.oauth_scopes_jsonb
                                ELSE NULL
                            END,
                            CASE
                                WHEN ss.scopes_array_jsonb IS NOT NULL
                                    AND jsonb_array_length(ss.scopes_array_jsonb) > 0 THEN ss.scopes_array_jsonb
                                ELSE NULL
                            END,
                            CASE
                                WHEN ss.scopes_text_jsonb IS NOT NULL
                                    AND jsonb_array_length(ss.scopes_text_jsonb) > 0 THEN ss.scopes_text_jsonb
                                ELSE NULL
                            END
                        ) AS normalized_scope_jsonb
                    FROM scope_sources AS ss
                )
                SELECT
                    sn.id IS NOT NULL AS joined_to_scope_normalized,
                    sn.normalized_scope_jsonb,
                    jsonb_array_length(sn.normalized_scope_jsonb) AS normalized_scope_len,
                    eal.scopes IS NULL AS scopes_is_null,
                    eal.scopes AS persisted_scopes
                FROM external_account_links AS eal
                LEFT JOIN scope_normalized AS sn ON sn.id = eal.id
                WHERE eal.id = :id
                """
            ),
            {"id": link_id},
        )
        .mappings()
        .one()
    )


def _run_backfill_upgrade(db_session: sa.orm.Session) -> None:
    module = _load_backfill_migration_module()
    module.op.execute = lambda sql: db_session.execute(sa.text(sql))
    module.upgrade()
    db_session.flush()


@pytest.mark.parametrize(
    ("metadata", "expected_scopes"),
    [
        ({"scopes": "identity wantlist"}, ["identity", "wantlist"]),
        ({"scopes": "  identity   wantlist  "}, ["identity", "wantlist"]),
        ({"scopes": "identity\t\nwantlist"}, ["identity", "wantlist"]),
        ({"scope": "identity inventory"}, ["identity", "inventory"]),
        ({"scopes": ["identity", "wantlist"]}, ["identity", "wantlist"]),
        ({"oauth_scopes": ["identity", "wantlist"]}, ["identity", "wantlist"]),
        ({"scopes": "   "}, None),
    ],
)
def test_backfill_migration_upgrade_normalizes_scope_variants(
    db_session,
    user,
    metadata: dict[str, object],
    expected_scopes: list[str] | None,
) -> None:
    token_metadata = {
        "refresh_token": "refresh-from-metadata",
        "token_type": "Bearer",
        "expires_at": "2030-01-01T00:00:00+00:00",
        **metadata,
    }
    link = DiscogsImportService().connect_account(
        db_session,
        user_id=user.id,
        external_user_id="discogs-user",
        access_token="access-token",
        token_metadata=token_metadata,
    )
    link.refresh_token = None
    link.token_type = None
    link.scopes = None
    link.access_token_expires_at = None
    db_session.add(link)
    db_session.flush()

    raw_scope_text = db_session.execute(
        sa.text(
            """
            SELECT COALESCE(token_metadata ->> 'scopes', token_metadata ->> 'scope')
            FROM external_account_links
            WHERE id = :id
            """
        ),
        {"id": link.id},
    ).scalar_one()
    before_scopes = db_session.execute(
        sa.text("SELECT scopes FROM external_account_links WHERE id = :id"),
        {"id": link.id},
    ).scalar_one()
    assert before_scopes is None
    if isinstance(metadata.get("scopes"), str):
        assert raw_scope_text == metadata["scopes"]

    _run_backfill_upgrade(db_session)
    db_session.refresh(link)

    after_scopes = db_session.execute(
        sa.text("SELECT scopes FROM external_account_links WHERE id = :id"),
        {"id": link.id},
    ).scalar_one()

    debug_row = _select_scope_debug_row(db_session, link_id=link.id)
    predicate_row = _select_scope_update_predicate_state(db_session, link_id=link.id)

    assert link.refresh_token == "refresh-from-metadata"
    assert link.token_type == "Bearer"
    assert link.access_token_expires_at == datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
    if metadata == {"scopes": "identity wantlist"}:
        assert after_scopes == ["identity", "wantlist"], (
            "scope write path failed despite scalar backfill success: "
            f"refresh={link.refresh_token!r}, token_type={link.token_type!r}, "
            f"expires={link.access_token_expires_at!r}, "
            f"normalized_candidate={debug_row['normalized_scope_jsonb']!r}, "
            f"persisted={debug_row['persisted_scopes']!r}, "
            f"joined={predicate_row['joined_to_scope_normalized']!r}, "
            f"len={predicate_row['normalized_scope_len']!r}, "
            f"scopes_is_null={predicate_row['scopes_is_null']!r}"
        )
    assert link.scopes == expected_scopes, (
        "migration scope backfill mismatch: "
        f"raw={debug_row['raw_scope_text']!r}, "
        f"normalized_text={debug_row['normalized_scope_text']!r}, "
        f"oauth_array={debug_row['oauth_scopes_jsonb']!r}, "
        f"scopes_array={debug_row['scopes_array_jsonb']!r}, "
        f"scopes_text={debug_row['scopes_text_jsonb']!r}, "
        f"normalized_jsonb={debug_row['normalized_scope_jsonb']!r}, "
        f"persisted_scopes={debug_row['persisted_scopes']!r}, "
        f"db_scopes={after_scopes!r}, "
        f"joined={predicate_row['joined_to_scope_normalized']!r}, "
        f"len={predicate_row['normalized_scope_len']!r}, "
        f"scopes_is_null={predicate_row['scopes_is_null']!r}"
    )
    assert after_scopes == expected_scopes


def test_backfill_migration_upgrade_is_idempotent_for_scopes(db_session, user) -> None:
    link = DiscogsImportService().connect_account(
        db_session,
        user_id=user.id,
        external_user_id="discogs-user",
        access_token="access-token",
        token_metadata={
            "refresh_token": "refresh-from-metadata",
            "token_type": "Bearer",
            "expires_at": "2030-01-01T00:00:00+00:00",
            "scopes": "identity wantlist",
        },
    )
    link.scopes = None
    db_session.add(link)
    db_session.flush()

    _run_backfill_upgrade(db_session)
    db_session.refresh(link)
    first_value: list[str] = list(link.scopes or [])
    first_value_sql = db_session.execute(
        sa.text("SELECT scopes FROM external_account_links WHERE id = :id"),
        {"id": link.id},
    ).scalar_one()

    _run_backfill_upgrade(db_session)
    db_session.refresh(link)
    second_value_sql = db_session.execute(
        sa.text("SELECT scopes FROM external_account_links WHERE id = :id"),
        {"id": link.id},
    ).scalar_one()

    assert link.scopes == first_value
    assert second_value_sql == first_value_sql == ["identity", "wantlist"]


def test_discogs_status_backfills_missing_normalized_fields_from_metadata(db_session, user) -> None:
    service = DiscogsImportService()
    link = service.connect_account(
        db_session,
        user_id=user.id,
        external_user_id="discogs-user",
        access_token="access-token",
        token_metadata={
            "refresh_token": "metadata-refresh",
            "token_type": "Bearer",
            "scope": "identity inventory",
            "expires_at": "2030-01-01T00:00:00+00:00",
        },
    )

    link.refresh_token = None
    link.token_type = None
    link.scopes = None
    link.access_token_expires_at = None
    db_session.add(link)
    db_session.flush()

    hydrated_link = service.get_status(db_session, user_id=user.id)
    assert hydrated_link is not None
    assert hydrated_link.refresh_token == "metadata-refresh"
    assert hydrated_link.token_type == "Bearer"
    assert hydrated_link.scopes == ["identity", "inventory"]
    assert hydrated_link.access_token_expires_at == datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_discogs_connect_account_preserves_existing_lifecycle_fields_when_omitted(db_session, user) -> None:
    service = DiscogsImportService()
    original_expiry = datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
    service.connect_account(
        db_session,
        user_id=user.id,
        external_user_id="discogs-user",
        access_token="access-token-1",
        token_metadata={"oauth_connected": True},
        refresh_token="existing-refresh",
        token_type="Bearer",
        scopes=["identity"],
        access_token_expires_at=original_expiry,
    )

    updated = service.connect_account(
        db_session,
        user_id=user.id,
        external_user_id="discogs-user",
        access_token="access-token-2",
        token_metadata={"oauth_connected": True},
    )

    assert updated.refresh_token == "existing-refresh"
    assert updated.token_type == "Bearer"
    assert updated.scopes == ["identity"]
    assert updated.access_token_expires_at == original_expiry
