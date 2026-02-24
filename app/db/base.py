from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings


def _build_engine():
    pool_mode = (settings.db_pool or "queue").lower()
    db_url = make_url(settings.database_url)

    # SQLite engines don't accept queue-pool kwargs like max_overflow/pool_size.
    # Keep local/dev and lightweight test setups working when DATABASE_URL uses sqlite.
    if db_url.get_backend_name() == "sqlite":
        connect_args = {"check_same_thread": False}
        engine_kwargs = {
            "pool_pre_ping": True,
            "future": True,
            "connect_args": connect_args,
        }
        if db_url.database in {None, "", ":memory:"}:
            engine_kwargs["poolclass"] = StaticPool

        return create_engine(settings.database_url, **engine_kwargs)

    if pool_mode == "null":
        return create_engine(
            settings.database_url,
            poolclass=NullPool,
            pool_pre_ping=True,
            future=True,
        )

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        future=True,
    )


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
