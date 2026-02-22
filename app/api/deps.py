from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.base import SessionLocal


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except:
        db.rollback()
        raise
    finally:
        db.close()
