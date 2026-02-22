from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

# --- Force test settings early (before app import) ---
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("JSON_LOGS", "false")
os.environ.setdefault("PROVIDER_FORCE_MOCK", "1")

os.environ.setdefault("DISCOGS_USER_AGENT", "test-agent")
os.environ.setdefault("DISCOGS_TOKEN", "test-token")

os.environ.setdefault("DB_POOL", "queue")
os.environ.setdefault("DB_POOL_SIZE", "5")
os.environ.setdefault("DB_MAX_OVERFLOW", "10")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set for tests (point it to a Postgres DB).")

from app.api.deps import get_db  # noqa: E402
from app.db.models import User  # noqa: E402
from app.main import create_app  # noqa: E402

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionTesting = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _smoke_db_connection() -> None:
    # quick sanity check that DB is reachable
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


@pytest.fixture()
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    trans = connection.begin()

    session = SessionTesting(bind=connection)

    # Start a SAVEPOINT so tests can rollback without wiping schema.
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess: Session, txn) -> None:
        # Automatically restart SAVEPOINT after each commit/rollback inside the test.
        if txn.nested and not txn._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user(db_session: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        display_name="Test User",
        is_active=True,
    )
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture()
def user2(db_session: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        display_name="Other User",
        is_active=True,
    )
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture()
def headers():
    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        return {"X-User-Id": str(user_id)}

    return _headers
