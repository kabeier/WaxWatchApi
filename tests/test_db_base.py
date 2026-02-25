from __future__ import annotations

from sqlalchemy.pool import NullPool, StaticPool

from app.db import base


def test_build_engine_uses_static_pool_for_sqlite_memory(monkeypatch):
    monkeypatch.setattr(base.settings, "database_url", "sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(base.settings, "db_pool", "queue")

    engine = base._build_engine()
    try:
        assert isinstance(engine.pool, StaticPool)
    finally:
        engine.dispose()


def test_build_engine_uses_default_pool_for_sqlite_file(monkeypatch):
    monkeypatch.setattr(base.settings, "database_url", "sqlite+pysqlite:///./db-base-test.db")
    monkeypatch.setattr(base.settings, "db_pool", "queue")

    engine = base._build_engine()
    try:
        assert not isinstance(engine.pool, StaticPool)
    finally:
        engine.dispose()


def test_build_engine_uses_null_pool_when_requested(monkeypatch):
    monkeypatch.setattr(base.settings, "database_url", "postgresql+psycopg://u:p@localhost/test")
    monkeypatch.setattr(base.settings, "db_pool", "null")

    engine = base._build_engine()
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()


def test_build_engine_uses_queue_pool_with_configured_sizes(monkeypatch):
    monkeypatch.setattr(base.settings, "database_url", "postgresql+psycopg://u:p@localhost/test")
    monkeypatch.setattr(base.settings, "db_pool", "queue")
    monkeypatch.setattr(base.settings, "db_pool_size", 4)
    monkeypatch.setattr(base.settings, "db_max_overflow", 9)

    engine = base._build_engine()
    try:
        assert engine.pool.size() == 4
        assert engine.pool._max_overflow == 9
    finally:
        engine.dispose()
