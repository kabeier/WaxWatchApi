from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.models import Base


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    engine = create_engine(url, future=True)

    with engine.connect() as conn:
        mc = MigrationContext.configure(conn)
        diffs = compare_metadata(mc, Base.metadata)

    if diffs:
        print("Schema drift detected (models != database).", file=sys.stderr)
        for d in diffs:
            print(f" - {d}", file=sys.stderr)
        return 1

    print("Schema OK (no drift).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
