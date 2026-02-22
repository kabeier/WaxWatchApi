from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _build_engine():
    pool_mode = (settings.db_pool or "queue").lower()

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
